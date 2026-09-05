"use client";

import { useQuery } from "@tanstack/react-query";
import { PackagePlus, Search } from "lucide-react";
import { useState } from "react";

import { StockAdjustDialog } from "@/components/admin/stock-adjust-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { StockLevel } from "@/lib/api/admin-types";
import { inventoryApi } from "@/lib/api/endpoints";
import { formatMoney } from "@/lib/format";
import { useDebounced } from "@/lib/hooks/use-debounced";
import { Permission } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function InventoryPage() {
  const canAdjust = useAuthStore((s) => s.permissions.has(Permission.STOCK_ADJUST));
  const currency = useAuthStore((s) => s.currency) ?? "USD";
  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  const [lowOnly, setLowOnly] = useState(false);
  const [selected, setSelected] = useState<StockLevel | null>(null);

  const levels = useQuery({
    queryKey: ["inventory", "levels", debouncedSearch, lowOnly],
    queryFn: () =>
      inventoryApi.levels({
        search: debouncedSearch || undefined,
        low_only: lowOnly || undefined,
        size: 100,
      }),
  });

  const items = levels.data?.items ?? [];
  const totalValue = items.reduce(
    (sum, item) => sum + Number.parseFloat(item.stock_value),
    0,
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Inventory"
        description="Stock on hand per branch, with a full movement history."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative max-w-sm flex-1">
          <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search name or SKU"
            className="pl-9"
          />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={lowOnly} onCheckedChange={setLowOnly} id="low-only" />
          Low stock only
        </label>
        <div className="flex-1" />
        <Card className="py-2">
          <CardContent className="flex items-baseline gap-2 px-4 py-0">
            <span className="text-muted-foreground text-sm">Stock value shown</span>
            <span className="numeric font-semibold">
              {formatMoney(totalValue, currency)}
            </span>
          </CardContent>
        </Card>
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Branch</TableHead>
                <TableHead className="text-right">On hand</TableHead>
                <TableHead className="text-right">Reorder at</TableHead>
                <TableHead className="text-right">Value</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {levels.isPending &&
                Array.from({ length: 6 }).map((_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={6}>
                      <Skeleton className="h-6 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!levels.isPending && items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="text-muted-foreground py-14 text-center"
                  >
                    {lowOnly
                      ? "Nothing is below its reorder level."
                      : "No stocked products."}
                  </TableCell>
                </TableRow>
              )}

              {items.map((item) => {
                const quantity = Number.parseFloat(item.quantity);
                return (
                  <TableRow key={`${item.product_id}-${item.branch_id}`}>
                    <TableCell>
                      <span className="block font-medium">{item.product_name}</span>
                      <span className="numeric text-muted-foreground block text-xs">
                        {item.sku}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {item.branch_name}
                    </TableCell>
                    <TableCell className="text-right">
                      <Badge
                        variant={
                          quantity <= 0
                            ? "destructive"
                            : item.is_low
                              ? "secondary"
                              : "outline"
                        }
                        className="numeric"
                      >
                        {quantity} {item.unit !== "piece" && item.unit}
                      </Badge>
                    </TableCell>
                    <TableCell className="numeric text-muted-foreground text-right">
                      {Number.parseFloat(item.low_stock_threshold) || "—"}
                    </TableCell>
                    <TableCell className="numeric text-right">
                      {formatMoney(item.stock_value, currency)}
                    </TableCell>
                    <TableCell>
                      {canAdjust && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setSelected(item)}
                        >
                          <PackagePlus className="size-4" /> Adjust
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <StockAdjustDialog
        item={selected}
        open={selected !== null}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  );
}
