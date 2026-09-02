"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { platformApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import type { TenantSummary } from "@/lib/api/platform-types";

/**
 * Blocking a shop stops it trading on the very next request and signs out
 * every till. That is severe enough to warrant a confirmation step and a
 * required reason -- the reason is shown to the shop, so "why can't I sell?"
 * has an answer without a support ticket.
 */
export function BlockTenantDialog({
  tenant,
  open,
  onOpenChange,
}: {
  tenant: TenantSummary | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");

  const block = useMutation({
    mutationFn: () => platformApi.setTenantStatus(tenant!.id, "suspended", reason),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["platform"] });
      toast.success(`${tenant?.name} suspended. Their tills are signed out.`);
      setReason("");
      onOpenChange(false);
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not suspend the shop.",
      ),
  });

  if (!tenant) return null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <div className="bg-destructive/10 text-destructive mb-2 flex size-11 items-center justify-center rounded-xl">
            <ShieldAlert className="size-5" />
          </div>
          <DialogTitle>Suspend {tenant.name}?</DialogTitle>
          <DialogDescription>
            They stop trading immediately and every open till is signed out. Their
            data and sales history are kept.
          </DialogDescription>
        </DialogHeader>

        <Field>
          <FieldLabel htmlFor="reason">Reason</FieldLabel>
          <Input
            id="reason"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder="Payment failed"
            autoFocus
          />
          <FieldDescription>
            Shown to the shop when they try to sign in.
          </FieldDescription>
        </Field>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={() => block.mutate()}
            disabled={!reason.trim() || block.isPending}
          >
            {block.isPending && <Loader2 className="size-4 animate-spin" />}
            Suspend shop
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
