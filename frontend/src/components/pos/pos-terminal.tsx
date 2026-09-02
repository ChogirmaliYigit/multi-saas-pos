"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  Loader2,
  Printer,
  ScanBarcode,
  Search,
  Wallet,
  X,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { CartPanel } from "@/components/pos/cart-panel";
import { PaymentDialog } from "@/components/pos/payment-dialog";
import { PrinterSettings } from "@/components/pos/printer-settings";
import { ProductGrid } from "@/components/pos/product-grid";
import { SaleCompleteDialog } from "@/components/pos/sale-complete-dialog";
import { ShiftGate } from "@/components/pos/shift-gate";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea, ScrollBar } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { isApiError } from "@/lib/api/errors";
import type { PaymentMethod, Product, Receipt } from "@/lib/api/pos-types";
import { catalogApi, ordersApi, shiftsApi } from "@/lib/api/endpoints";
import { useBarcodeScanner } from "@/lib/pos/use-barcode-scanner";
import { usePrintReceipt } from "@/lib/pos/use-print-receipt";
import { computeTotals, useCartStore } from "@/lib/stores/cart-store";
import { useAuthStore } from "@/lib/stores/auth-store";
import { usePrinterStore } from "@/lib/stores/printer-store";
import { cn } from "@/lib/utils";

export function PosTerminal() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const printReceipt = usePrintReceipt();
  const autoPrint = usePrinterStore((s) => s.autoPrint);
  const transport = usePrinterStore((s) => s.transport);

  const [search, setSearch] = useState("");
  const [categoryId, setCategoryId] = useState<string | null>(null);
  const [paymentOpen, setPaymentOpen] = useState(false);
  const [printerOpen, setPrinterOpen] = useState(false);
  const [completed, setCompleted] = useState<Receipt | null>(null);
  const [lastScan, setLastScan] = useState<string | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const lines = useCartStore((s) => s.lines);
  const orderDiscountKind = useCartStore((s) => s.orderDiscountKind);
  const orderDiscountValue = useCartStore((s) => s.orderDiscountValue);
  const addProduct = useCartStore((s) => s.addProduct);
  const clearCart = useCartStore((s) => s.clear);
  const idempotencyKey = useCartStore((s) => s.idempotencyKey);

  const totals = useMemo(
    () => computeTotals(lines, orderDiscountKind, orderDiscountValue),
    [lines, orderDiscountKind, orderDiscountValue],
  );

  const shiftQuery = useQuery({
    queryKey: ["shift", "current"],
    queryFn: shiftsApi.current,
    staleTime: 60_000,
  });

  const categoriesQuery = useQuery({
    queryKey: ["catalog", "categories"],
    queryFn: catalogApi.categories,
    staleTime: 5 * 60_000,
    enabled: Boolean(shiftQuery.data),
  });

  const productsQuery = useQuery({
    queryKey: ["catalog", "products", search, categoryId],
    queryFn: () =>
      catalogApi.products({
        search: search || undefined,
        category_id: categoryId ?? undefined,
        size: 120,
      }),
    enabled: Boolean(shiftQuery.data),
    staleTime: 30_000,
  });

  const openShift = useMutation({
    mutationFn: shiftsApi.open,
    onSuccess: (shift) => {
      queryClient.setQueryData(["shift", "current"], shift);
      toast.success("Shift open. Ready to sell.");
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not open the shift."),
  });

  /**
   * Resolve a scanned code and drop it in the cart.
   *
   * A scan that finds nothing must be loud -- a silent failure means the
   * cashier bags an item the customer was never charged for.
   */
  const handleScan = useCallback(
    async (code: string) => {
      setLastScan(code);
      try {
        const result = await catalogApi.lookup(code);
        // Scanning a carton barcode adds the whole case, not one unit.
        addProduct(result.product, Number.parseFloat(result.pack_size) || 1);
        if (result.matched_on === "pack_barcode") {
          const packs = Number.parseFloat(result.pack_size);
          toast.success(`${result.product.name} \u00d7${packs}`);
        }
      } catch (error) {
        toast.error(
          isApiError(error) && error.code === "product_not_found"
            ? `Unknown barcode ${code}`
            : "Lookup failed. Try again.",
        );
      }
    },
    [addProduct],
  );

  useBarcodeScanner({
    onScan: handleScan,
    // Disabled while a modal is open: a scan landing in the cart behind the
    // payment dialog would change the total the cashier is looking at.
    enabled: !paymentOpen && !printerOpen && completed === null,
  });

  const checkout = useMutation({
    mutationFn: async (
      payments: {
        method: PaymentMethod;
        amount: string;
        tendered_amount?: string;
        card_last4?: string;
      }[],
    ) => {
      const order = await ordersApi.create({
        items: lines.map((line) => ({
          product_id: line.productId,
          quantity: (line.quantityMilli / 1000).toFixed(3),
          ...(line.discountKind !== "none"
            ? {
                discount_type: line.discountKind,
                discount_value: String(line.discountValue),
              }
            : {}),
        })),
        payments,
        ...(orderDiscountKind !== "none"
          ? {
              discount_type: orderDiscountKind,
              discount_value: String(orderDiscountValue),
            }
          : {}),
        idempotency_key: idempotencyKey,
      });
      return ordersApi.receipt(order.id);
    },
    onSuccess: async (receipt) => {
      setPaymentOpen(false);
      setCompleted(receipt);
      clearCart();
      // Stock changed, so the grid's counts are stale.
      await queryClient.invalidateQueries({ queryKey: ["catalog", "products"] });
      await queryClient.invalidateQueries({ queryKey: ["shift"] });
      // Only auto-print to a directly connected printer. With the PDF
      // fallback this would throw the browser's modal print dialog in the
      // cashier's face on every single sale; they press Print instead.
      if (autoPrint && transport) void printReceipt(receipt);
    },
    onError: (error) => {
      if (!isApiError(error)) {
        toast.error("Checkout failed. Try again.");
        return;
      }
      // These three are the ones a cashier can actually act on, so they get
      // wording that says what to do rather than what went wrong.
      if (error.code === "insufficient_stock") {
        toast.error("Not enough stock for one of these items.");
      } else if (error.code === "no_open_shift") {
        toast.error("Your shift closed. Open the till again.");
        void queryClient.invalidateQueries({ queryKey: ["shift"] });
      } else {
        toast.error(error.message);
      }
    },
  });

  // Keyboard shortcuts. A till is driven at speed with one hand on the
  // scanner, so the important actions must not need the mouse.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "F2" && lines.length > 0) {
        event.preventDefault();
        setPaymentOpen(true);
      }
      if (event.key === "F3") {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape" && document.activeElement === searchRef.current) {
        setSearch("");
        searchRef.current?.blur();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [lines.length]);

  if (shiftQuery.isPending) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Loader2 className="text-muted-foreground size-6 animate-spin" />
      </div>
    );
  }

  if (!shiftQuery.data) {
    return (
      <>
        <TerminalHeader
          userName={user?.full_name}
          onPrinter={() => setPrinterOpen(true)}
        />
        <ShiftGate
          onOpen={(float) => openShift.mutate(float)}
          isPending={openShift.isPending}
        />
        <PrinterSettings open={printerOpen} onOpenChange={setPrinterOpen} />
      </>
    );
  }

  const currency = completed?.order.currency ?? "USD";
  const categories = categoriesQuery.data ?? [];

  return (
    <>
      <TerminalHeader
        userName={user?.full_name}
        onPrinter={() => setPrinterOpen(true)}
        lastScan={lastScan}
        shiftOpen
      />

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="bg-background flex shrink-0 items-center gap-2 border-b p-3">
            <div className="relative flex-1">
              <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
              <Input
                ref={searchRef}
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search or scan  ·  F3"
                className="h-11 pl-9"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="text-muted-foreground hover:bg-accent absolute top-1/2 right-2 -translate-y-1/2 rounded p-1"
                  aria-label="Clear search"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
          </div>

          <ScrollArea className="bg-background shrink-0 border-b">
            <div className="flex gap-2 p-3">
              <CategoryChip
                active={categoryId === null}
                onClick={() => setCategoryId(null)}
                label="All"
              />
              {categories.map((category) => (
                <CategoryChip
                  key={category.id}
                  active={categoryId === category.id}
                  onClick={() => setCategoryId(category.id)}
                  label={category.name}
                  color={category.color}
                />
              ))}
              {categoriesQuery.isPending &&
                Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-9 w-24 rounded-full" />
                ))}
            </div>
            <ScrollBar orientation="horizontal" />
          </ScrollArea>

          <ScrollArea className="flex-1">
            <div className="p-3">
              <ProductGrid
                products={productsQuery.data?.items ?? []}
                currency={currency}
                isLoading={productsQuery.isPending}
                onSelect={(product: Product) => addProduct(product, 1)}
              />
            </div>
          </ScrollArea>
        </div>

        <CartPanel
          currency={currency}
          totals={totals}
          onCheckout={() => setPaymentOpen(true)}
          checkoutDisabled={checkout.isPending}
        />
      </div>

      <PaymentDialog
        open={paymentOpen}
        onOpenChange={setPaymentOpen}
        totalCents={totals.total}
        currency={currency}
        isSubmitting={checkout.isPending}
        onConfirm={(payments) => checkout.mutate(payments)}
      />

      <SaleCompleteDialog
        receipt={completed}
        open={completed !== null}
        onOpenChange={(open) => !open && setCompleted(null)}
        onPrint={() => completed && void printReceipt(completed, { copy: true })}
        onNewSale={() => setCompleted(null)}
      />

      <PrinterSettings open={printerOpen} onOpenChange={setPrinterOpen} />
    </>
  );
}

function TerminalHeader({
  userName,
  onPrinter,
  lastScan,
  shiftOpen = false,
}: {
  userName?: string;
  onPrinter: () => void;
  lastScan?: string | null;
  shiftOpen?: boolean;
}) {
  const transport = usePrinterStore((s) => s.transport);

  return (
    <header className="bg-background flex h-14 shrink-0 items-center gap-2 border-b px-3">
      <Button asChild variant="ghost" size="sm" className="gap-2">
        <Link href="/dashboard">
          <ArrowLeft className="size-4" />
          <span className="hidden sm:inline">Admin</span>
        </Link>
      </Button>

      <div className="text-muted-foreground flex items-center gap-1.5">
        <ScanBarcode className="size-4" />
        <span className="numeric hidden text-xs sm:inline">
          {lastScan ? lastScan : "Scanner ready"}
        </span>
      </div>

      <div className="flex-1" />

      <Button variant="ghost" size="sm" onClick={onPrinter} className="gap-2">
        <Printer className="size-4" />
        <span className="hidden sm:inline">
          {transport ? transport.label : "Printer"}
        </span>
      </Button>

      {shiftOpen && (
        <Badge variant="outline" className="gap-1.5">
          <Wallet className="size-3" />
          Shift open
        </Badge>
      )}

      <span className="text-muted-foreground hidden text-sm sm:inline">
        {userName}
      </span>
    </header>
  );
}

function CategoryChip({
  active,
  onClick,
  label,
  color,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  color?: string | null;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "touch-target flex shrink-0 items-center gap-2 rounded-full border px-4 text-sm whitespace-nowrap transition-colors",
        active ? "border-primary bg-primary/10 font-medium" : "hover:bg-accent",
      )}
    >
      {color && (
        <span
          className="size-2 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden
        />
      )}
      {label}
    </button>
  );
}
