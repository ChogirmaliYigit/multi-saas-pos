"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  Loader2,
  MoreHorizontal,
  Package,
  Plus,
  Receipt,
  Star,
  Users,
} from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { Branch } from "@/lib/api/admin-types";
import { branchesApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { Permission } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function BranchesPage() {
  const canManage = useAuthStore((s) =>
    s.permissions.has(Permission.BRANCH_MANAGE),
  );
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<Branch | null>(null);

  const branches = useQuery({
    queryKey: ["branches"],
    queryFn: () => branchesApi.list(),
  });

  const items = branches.data ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Branches"
        description="Shop locations and their stock."
        actions={
          canManage && (
            <Button onClick={() => setCreating(true)}>
              <Plus className="size-4" /> Add branch
            </Button>
          )
        }
      />

      {branches.isPending ? (
        <div className="grid gap-4 md:grid-cols-2">
          {Array.from({ length: 2 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full" />
          ))}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {items.map((branch) => (
            <BranchCard
              key={branch.id}
              branch={branch}
              canManage={canManage}
              isOnly={items.length === 1}
              onEdit={() => setEditing(branch)}
            />
          ))}
        </div>
      )}

      <BranchDialog
        open={creating || editing !== null}
        branch={editing}
        onOpenChange={(open) => {
          if (!open) {
            setCreating(false);
            setEditing(null);
          }
        }}
      />
    </div>
  );
}

function BranchCard({
  branch,
  canManage,
  isOnly,
  onEdit,
}: {
  branch: Branch;
  canManage: boolean;
  isOnly: boolean;
  onEdit: () => void;
}) {
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["branches"] });

  const makeDefault = useMutation({
    mutationFn: () => branchesApi.update(branch.id, { is_default: true }),
    onSuccess: async () => {
      await invalidate();
      toast.success(`${branch.name} is now the default branch.`);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not update."),
  });

  const close = useMutation({
    mutationFn: () => branchesApi.remove(branch.id),
    onSuccess: async (result) => {
      await invalidate();
      setConfirming(false);
      toast.success(result.message);
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not close the branch.",
      ),
  });

  return (
    <Card className="gap-4 p-5">
      <div className="flex items-start gap-3">
        <span className="bg-muted flex size-10 shrink-0 items-center justify-center rounded-lg">
          <Building2 className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="truncate font-medium">{branch.name}</h3>
            <Badge variant="outline" className="font-mono text-xs">
              {branch.code}
            </Badge>
            {branch.is_default && (
              <Badge className="gap-1">
                <Star className="size-3" /> Default
              </Badge>
            )}
            {!branch.is_active && <Badge variant="secondary">Inactive</Badge>}
          </div>
          <p className="text-muted-foreground mt-1 truncate text-sm">
            {branch.address || "No address set"}
          </p>
          {branch.phone && (
            <p className="text-muted-foreground text-sm">{branch.phone}</p>
          )}
        </div>

        {canManage && (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                aria-label={`Actions for ${branch.name}`}
              >
                <MoreHorizontal className="size-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onEdit}>Edit details</DropdownMenuItem>
              {!branch.is_default && (
                <DropdownMenuItem
                  disabled={makeDefault.isPending}
                  onClick={() => makeDefault.mutate()}
                >
                  <Star className="size-4" /> Make default
                </DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant="destructive"
                /* The API refuses both of these too; disabling here just
                   avoids offering an action that cannot succeed. */
                disabled={isOnly || branch.is_default}
                onClick={() => setConfirming(true)}
              >
                Close branch
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        )}
      </div>

      <dl className="grid grid-cols-3 gap-2 text-center">
        <Stat icon={Users} label="Staff" value={branch.staff_count} />
        <Stat icon={Package} label="Products" value={branch.product_count} />
        <Stat
          icon={Receipt}
          label="Sales / 30d"
          value={branch.orders_last_30_days}
        />
      </dl>

      <Dialog open={confirming} onOpenChange={setConfirming}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Close {branch.name}?</DialogTitle>
            <DialogDescription>
              It stops appearing at the till. Its past sales, receipts and stock
              history are kept — closing a branch never erases what it sold.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirming(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={close.isPending}
              onClick={() => close.mutate()}
            >
              {close.isPending && <Loader2 className="size-4 animate-spin" />}
              Close branch
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof Users;
  label: string;
  value: number;
}) {
  return (
    <div className="bg-muted/50 rounded-lg px-2 py-3">
      <dt className="text-muted-foreground flex items-center justify-center gap-1 text-xs">
        <Icon className="size-3" /> {label}
      </dt>
      <dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

function BranchDialog({
  open,
  branch,
  onOpenChange,
}: {
  open: boolean;
  branch: Branch | null;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <BranchForm
          key={branch?.id ?? "new"}
          branch={branch}
          onDone={() => onOpenChange(false)}
        />
      </DialogContent>
    </Dialog>
  );
}

function BranchForm({
  branch,
  onDone,
}: {
  branch: Branch | null;
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: branch?.name ?? "",
    code: branch?.code ?? "",
    address: branch?.address ?? "",
    phone: branch?.phone ?? "",
  });

  const save = useMutation({
    mutationFn: () => {
      const shared = {
        name: form.name.trim(),
        address: form.address.trim() || null,
        phone: form.phone.trim() || null,
      };
      return branch
        ? branchesApi.update(branch.id, shared)
        : branchesApi.create({ ...shared, code: form.code.trim() });
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["branches"] });
      toast.success(branch ? "Branch updated." : "Branch added.");
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.isBillingBlock) {
        toast.error(error.message, { duration: 8000 });
        return;
      }
      toast.error(isApiError(error) ? error.message : "Could not save the branch.");
    },
  });

  const canSave = form.name.trim() && (branch || form.code.trim());

  return (
    <>
      <DialogHeader>
        <DialogTitle>{branch ? "Edit branch" : "Add branch"}</DialogTitle>
        <DialogDescription>
          Stock is counted per branch, so each location sees its own levels.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-1">
        <Field>
          <FieldLabel htmlFor="branch-name">Name</FieldLabel>
          <Input
            id="branch-name"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            autoFocus
          />
        </Field>

        {branch ? (
          <Field>
            <FieldLabel>Code</FieldLabel>
            <Input value={branch.code} disabled className="font-mono" />
            <FieldDescription>
              Fixed after creation — it prefixes every receipt number this branch
              has issued.
            </FieldDescription>
          </Field>
        ) : (
          <Field>
            <FieldLabel htmlFor="branch-code">Code</FieldLabel>
            <Input
              id="branch-code"
              value={form.code}
              maxLength={32}
              className="font-mono uppercase"
              onChange={(e) =>
                setForm({ ...form, code: e.target.value.toUpperCase() })
              }
            />
            <FieldDescription>
              Short, like MAIN or AIR. Cannot be changed later.
            </FieldDescription>
          </Field>
        )}

        <Field>
          <FieldLabel htmlFor="branch-address">Address</FieldLabel>
          <Textarea
            id="branch-address"
            rows={2}
            value={form.address}
            onChange={(e) => setForm({ ...form, address: e.target.value })}
          />
          <FieldDescription>
            Printed on this branch&apos;s receipts.
          </FieldDescription>
        </Field>

        <Field>
          <FieldLabel htmlFor="branch-phone">Phone</FieldLabel>
          <Input
            id="branch-phone"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
        </Field>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button onClick={() => save.mutate()} disabled={!canSave || save.isPending}>
          {save.isPending && <Loader2 className="size-4 animate-spin" />}
          {branch ? "Save" : "Add branch"}
        </Button>
      </DialogFooter>
    </>
  );
}
