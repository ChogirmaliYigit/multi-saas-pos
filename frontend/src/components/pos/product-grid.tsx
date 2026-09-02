"use client";

import { motion } from "framer-motion";
import { PackageX } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { Product } from "@/lib/api/pos-types";
import { formatCents, toCents } from "@/lib/pos/money";
import { cn } from "@/lib/utils";

export function ProductGrid({
  products,
  currency,
  isLoading,
  onSelect,
}: {
  products: Product[];
  currency: string;
  isLoading: boolean;
  onSelect: (product: Product) => void;
}) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {Array.from({ length: 12 }).map((_, i) => (
          <Skeleton key={i} className="h-28 rounded-xl" />
        ))}
      </div>
    );
  }

  if (products.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
        <PackageX className="text-muted-foreground size-8" />
        <p className="font-medium">Nothing matches</p>
        <p className="text-muted-foreground text-sm">
          Try another search, or scan the item&apos;s barcode.
        </p>
      </div>
    );
  }

  return (
    <div className="pos-surface grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      {products.map((product) => {
        const outOfStock =
          product.track_stock &&
          Number.parseFloat(product.stock_quantity ?? "0") <= 0;

        return (
          <motion.button
            key={product.id}
            type="button"
            onClick={() => onSelect(product)}
            disabled={outOfStock}
            // A tap is confirmed by the tile shrinking under the finger.
            // On a touch screen with no hover, that press state is the only
            // feedback the cashier gets before the cart updates.
            whileTap={{ scale: 0.96 }}
            transition={{ type: "spring", stiffness: 600, damping: 30 }}
            className={cn(
              "group touch-target bg-card relative flex h-28 flex-col justify-between rounded-xl border p-3 text-left",
              "hover:border-primary/50 hover:bg-accent transition-colors",
              "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none",
              outOfStock && "hover:bg-card cursor-not-allowed opacity-50",
            )}
          >
            <span className="line-clamp-2 text-sm leading-snug font-medium">
              {product.name}
            </span>

            <span className="flex items-end justify-between gap-2">
              <span className="numeric text-base font-semibold">
                {formatCents(toCents(product.price), currency)}
              </span>
              {product.track_stock && (
                <Badge
                  variant={
                    outOfStock
                      ? "destructive"
                      : product.low_stock
                        ? "secondary"
                        : "outline"
                  }
                  className="numeric shrink-0 px-1.5 text-[10px]"
                >
                  {outOfStock
                    ? "Out"
                    : `${Number.parseFloat(product.stock_quantity ?? "0")}`}
                </Badge>
              )}
            </span>
          </motion.button>
        );
      })}
    </div>
  );
}
