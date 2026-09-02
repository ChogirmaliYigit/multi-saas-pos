"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Pencil, Plus, Search, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { ProductDialog } from "@/components/admin/product-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { productsApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { formatMoney } from "@/lib/format";
import { useDebounced } from "@/lib/hooks/use-debounced";
import { useAuthStore } from "@/lib/stores/auth-store";
import { Permission } from "@/lib/permissions";

export default function ProductsPage() {
  const queryClient = useQueryClient();
  const canManage = useAuthStore((s) =>
    s.permissions.has(Permission.PRODUCT_MANAGE),
  );
  const canSeeCost = useAuthStore((s) =>
    s.permissions.has(Permission.PRODUCT_COST_READ),
  );

  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounced(search, 300);
  // The id, not the row: a list row carries no description or tax rate, so
  // editing from it and saving would blank both. The dialog loads the full
  // record before showing the form.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const products = useQuery({
    queryKey: ["catalog", "admin-products", debouncedSearch],
    queryFn: () =>
      productsApi.list({ search: debouncedSearch || undefined, size: 100 }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => productsApi.remove(id),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["catalog"] });
      toast.success("Product removed. Past sales keep their record.");
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not remove the product.",
      ),
  });

  const items = products.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Products"
        description="SKUs, barcodes, pricing and stock levels."
        actions={
          canManage && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> New product
            </Button>
          )
        }
      />

      <div className="relative max-w-sm">
        <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search name, SKU or barcode"
          className="pl-9"
        />
      </div>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>SKU</TableHead>
                <TableHead className="text-right">Price</TableHead>
                {canSeeCost && <TableHead className="text-right">Cost</TableHead>}
                {canSeeCost && <TableHead className="text-right">Margin</TableHead>}
                <TableHead className="text-right">Stock</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.isPending &&
                Array.from({ length: 6 }).map((_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-6 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!products.isPending && items.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={7}
                    className="text-muted-foreground py-14 text-center"
                  >
                    {search ? "Nothing matches that search." : "No products yet."}
                  </TableCell>
                </TableRow>
              )}

              {items.map((product) => {
                const price = Number.parseFloat(product.price);
                // cost_price is null for roles without PRODUCT_COST_READ, so
                // margin is genuinely unknown rather than zero -- rendering a
                // computed 0% or NaN% would be worse than saying nothing.
                const cost =
                  product.cost_price === null
                    ? null
                    : Number.parseFloat(product.cost_price);
                const margin =
                  cost !== null && price > 0
                    ? ((price - cost) / price) * 100
                    : null;
                const stock = product.stock_quantity
                  ? Number.parseFloat(product.stock_quantity)
                  : null;

                return (
                  <TableRow key={product.id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {product.is_favorite && (
                          <Star className="text-muted-foreground size-3.5 shrink-0 fill-current" />
                        )}
                        <span className="font-medium">{product.name}</span>
                      </div>
                      {product.category_name && (
                        <span className="text-muted-foreground text-xs">
                          {product.category_name}
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="numeric text-muted-foreground">
                      {product.sku}
                    </TableCell>
                    <TableCell className="numeric text-right">
                      {formatMoney(price, "USD")}
                    </TableCell>
                    {canSeeCost && (
                      <TableCell className="numeric text-muted-foreground text-right">
                        {cost === null ? "—" : formatMoney(cost, "USD")}
                      </TableCell>
                    )}
                    {canSeeCost && (
                      <TableCell className="numeric text-muted-foreground text-right">
                        {margin === null ? "—" : `${margin.toFixed(0)}%`}
                      </TableCell>
                    )}
                    <TableCell className="text-right">
                      {!product.track_stock ? (
                        <span className="text-muted-foreground text-xs">
                          Not tracked
                        </span>
                      ) : (
                        <Badge
                          variant={
                            stock !== null && stock <= 0
                              ? "destructive"
                              : product.low_stock
                                ? "secondary"
                                : "outline"
                          }
                          className="numeric"
                        >
                          {stock ?? 0}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {canManage && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Actions for ${product.name}`}
                            >
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setEditingId(product.id)}
                            >
                              <Pencil className="size-4" /> Edit
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => remove.mutate(product.id)}
                            >
                              <Trash2 className="size-4" /> Remove
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      {products.data && products.data.total > items.length && (
        <p className="text-muted-foreground text-sm">
          Showing {items.length} of {products.data.total}. Narrow the search to see
          more.
        </p>
      )}

      <ProductDialog
        productId={editingId}
        open={editingId !== null || creating}
        onOpenChange={(open) => {
          if (!open) {
            setEditingId(null);
            setCreating(false);
          }
        }}
      />
    </div>
  );
}
