"use client";

import { AlertTriangle, PackageCheck } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import type { LowStockItem } from "@/lib/api/admin-types";

export function LowStockList({ items }: { items: LowStockItem[] }) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-10 text-center">
        <PackageCheck className="text-muted-foreground size-7" />
        <p className="text-muted-foreground text-sm">
          Everything is above its reorder level.
        </p>
      </div>
    );
  }

  return (
    <ul className="divide-y">
      {items.map((item) => {
        const quantity = Number.parseFloat(item.quantity);
        const out = quantity <= 0;
        return (
          <li key={`${item.product_id}-${item.branch_id}`}>
            <Link
              href="/inventory"
              className="hover:bg-accent/50 flex items-center gap-3 py-2.5 transition-colors"
            >
              <AlertTriangle
                className={
                  out ? "text-destructive size-4" : "text-muted-foreground size-4"
                }
              />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">
                  {item.name}
                </span>
                <span className="text-muted-foreground block truncate text-xs">
                  {item.sku} · {item.branch_name}
                </span>
              </span>
              {/* Status wears an icon and a word, never colour alone. */}
              <Badge
                variant={out ? "destructive" : "secondary"}
                className="numeric shrink-0"
              >
                {out ? "Out of stock" : `${quantity} left`}
              </Badge>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
