"use client";

import { useQuery } from "@tanstack/react-query";
import { Receipt, RotateCcw } from "lucide-react";
import { useState } from "react";

import { RefundDialog } from "@/components/admin/refund-dialog";
import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ordersApi } from "@/lib/api/endpoints";
import { formatDateTime, formatMoney } from "@/lib/format";
import { Permission } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

const STATUS: Record<
  string,
  { label: string; variant: "outline" | "secondary" | "destructive" }
> = {
  completed: { label: "Completed", variant: "outline" },
  partially_refunded: { label: "Part refunded", variant: "secondary" },
  refunded: { label: "Refunded", variant: "destructive" },
  voided: { label: "Voided", variant: "destructive" },
};

export default function SalesPage() {
  const canRefund = useAuthStore((s) => s.permissions.has(Permission.ORDER_REFUND));
  const [refunding, setRefunding] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const orders = useQuery({
    queryKey: ["orders", "list", page],
    queryFn: () => ordersApi.list({ page, size: 25 }),
  });

  const items = orders.data?.items ?? [];
  const total = orders.data?.total ?? 0;
  const pages = Math.ceil(total / 25);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Sales"
        description="Every completed order, and what has been returned."
      />

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Receipt</TableHead>
                <TableHead>When</TableHead>
                <TableHead className="text-right">Items</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="text-right">Refunded</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-24" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {orders.isPending &&
                Array.from({ length: 6 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell colSpan={7}>
                      <Skeleton className="h-7 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {!orders.isPending && items.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="py-16 text-center">
                    <Receipt className="text-muted-foreground mx-auto mb-2 size-7" />
                    <p className="text-muted-foreground text-sm">
                      No sales yet. Ring one up on the POS terminal.
                    </p>
                  </TableCell>
                </TableRow>
              )}

              {items.map((order) => {
                const refunded = Number(order.refunded_total ?? 0);
                const status = STATUS[order.status] ?? {
                  label: order.status,
                  variant: "outline" as const,
                };
                // Lines, not summed quantities: adding 1.738 kg of tomatoes
                // to 2 cans gives a number that means nothing, and summing
                // decimal strings as JS floats put 5.1259999999999994 on the
                // screen. A receipt counts lines.
                const lineCount = order.items.length;
                // Nothing left to give back once it is fully refunded.
                const refundable =
                  order.status !== "refunded" && order.status !== "voided";

                return (
                  <TableRow key={order.id}>
                    <TableCell className="numeric font-medium">
                      {order.order_number}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {order.completed_at
                        ? formatDateTime(order.completed_at)
                        : formatDateTime(order.created_at)}
                    </TableCell>
                    <TableCell className="numeric text-muted-foreground text-right">
                      {lineCount}
                    </TableCell>
                    <TableCell className="numeric text-right">
                      {formatMoney(order.total, order.currency)}
                    </TableCell>
                    <TableCell className="numeric text-right">
                      {refunded > 0 ? (
                        <span className="text-destructive">
                          −{formatMoney(refunded, order.currency)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant={status.variant}>{status.label}</Badge>
                    </TableCell>
                    <TableCell>
                      {canRefund && refundable && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setRefunding(order.id)}
                        >
                          <RotateCcw className="size-4" /> Refund
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

      {pages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">
            Page {page} of {pages} · {total} orders
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pages}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      <RefundDialog
        orderId={refunding}
        open={refunding !== null}
        onOpenChange={(open) => !open && setRefunding(null)}
      />
    </div>
  );
}
