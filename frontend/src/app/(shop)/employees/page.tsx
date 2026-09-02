"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, MoreHorizontal, Plus, UserX } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
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
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { employeesApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { formatDateTime, initials } from "@/lib/format";
import { Permission, ROLE_LABEL } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function EmployeesPage() {
  const queryClient = useQueryClient();
  const me = useAuthStore((s) => s.user);
  const canCreate = useAuthStore((s) => s.permissions.has(Permission.USER_CREATE));
  const canUpdate = useAuthStore((s) => s.permissions.has(Permission.USER_UPDATE));
  const canDelete = useAuthStore((s) => s.permissions.has(Permission.USER_DELETE));

  const [showInactive, setShowInactive] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const employees = useQuery({
    queryKey: ["employees", showInactive],
    queryFn: () => employeesApi.list({ include_inactive: showInactive }),
  });

  const setActive = useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      employeesApi.update(id, { is_active: isActive }),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["employees"] });
      toast.success(
        variables.isActive
          ? "Account reactivated."
          : "Account deactivated and signed out everywhere.",
      );
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not update the account.",
      ),
  });

  const items = employees.data?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employees"
        description="Who works here, and what each of them may do."
        actions={
          canCreate && (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" /> Add employee
            </Button>
          )
        }
      />

      <label className="flex w-fit items-center gap-2 text-sm">
        <Switch checked={showInactive} onCheckedChange={setShowInactive} />
        Show deactivated
      </label>

      <Card className="overflow-hidden p-0">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Terminal PIN</TableHead>
                <TableHead>Last signed in</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {employees.isPending &&
                Array.from({ length: 4 }).map((_, index) => (
                  <TableRow key={index}>
                    <TableCell colSpan={5}>
                      <Skeleton className="h-8 w-full" />
                    </TableCell>
                  </TableRow>
                ))}

              {items.map((employee) => {
                const isSelf = employee.id === me?.id;
                return (
                  <TableRow
                    key={employee.id}
                    className={employee.is_active ? "" : "opacity-55"}
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <Avatar className="size-8">
                          <AvatarFallback className="text-xs">
                            {initials(employee.full_name)}
                          </AvatarFallback>
                        </Avatar>
                        <div className="min-w-0">
                          <span className="block truncate font-medium">
                            {employee.full_name}
                            {isSelf && (
                              <span className="text-muted-foreground ml-2 text-xs">
                                You
                              </span>
                            )}
                          </span>
                          <span className="text-muted-foreground block truncate text-xs">
                            {employee.email}
                          </span>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          employee.role === "owner" ? "default" : "secondary"
                        }
                      >
                        {ROLE_LABEL[employee.role]}
                      </Badge>
                      {!employee.is_active && (
                        <Badge variant="outline" className="ml-2 gap-1">
                          <UserX className="size-3" /> Deactivated
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {employee.has_pin ? "Set" : "Not set"}
                    </TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {employee.last_login_at
                        ? formatDateTime(employee.last_login_at)
                        : "Never"}
                    </TableCell>
                    <TableCell>
                      {(canUpdate || canDelete) && !isSelf && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label={`Actions for ${employee.full_name}`}
                            >
                              <MoreHorizontal className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {employee.is_active ? (
                              <DropdownMenuItem
                                variant="destructive"
                                onClick={() =>
                                  setActive.mutate({
                                    id: employee.id,
                                    isActive: false,
                                  })
                                }
                              >
                                <UserX className="size-4" /> Deactivate
                              </DropdownMenuItem>
                            ) : (
                              <DropdownMenuItem
                                onClick={() =>
                                  setActive.mutate({
                                    id: employee.id,
                                    isActive: true,
                                  })
                                }
                              >
                                Reactivate
                              </DropdownMenuItem>
                            )}
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

      <CreateEmployeeDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function CreateEmployeeDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <CreateEmployeeForm onDone={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

function CreateEmployeeForm({ onDone }: { onDone: () => void }) {
  const queryClient = useQueryClient();
  const myRole = useAuthStore((s) => s.user?.role);
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    password: "",
    role: "cashier",
    pin: "",
  });

  const create = useMutation({
    mutationFn: () =>
      employeesApi.create({
        full_name: form.full_name.trim(),
        email: form.email.trim(),
        password: form.password,
        role: form.role,
        pin: form.pin || null,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["employees"] });
      toast.success("Employee added.");
      onDone();
    },
    onError: (error) => {
      if (isApiError(error) && error.isBillingBlock) {
        toast.error(error.message, { duration: 8000 });
        return;
      }
      toast.error(
        isApiError(error) ? error.message : "Could not add the employee.",
      );
    },
  });

  const canSave =
    form.full_name.trim() && form.email.trim() && form.password.length >= 10;

  return (
    <>
      <DialogHeader>
        <DialogTitle>Add employee</DialogTitle>
        <DialogDescription>
          They sign in with this email and password.
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-4 py-1">
        <Field>
          <FieldLabel htmlFor="emp-name">Full name</FieldLabel>
          <Input
            id="emp-name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            autoFocus
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="emp-email">Email</FieldLabel>
          <Input
            id="emp-email"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="emp-password">Temporary password</FieldLabel>
          <Input
            id="emp-password"
            type="text"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
          <FieldDescription>
            At least 10 characters. They can change it after signing in.
          </FieldDescription>
        </Field>
        <Field>
          <FieldLabel>Role</FieldLabel>
          <Select
            value={form.role}
            onValueChange={(value) => setForm({ ...form, role: value })}
          >
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="cashier">Cashier — till only</SelectItem>
              <SelectItem value="manager">
                Manager — inventory and reports
              </SelectItem>
              {/* Only an owner may create another owner; the API enforces it
                  too, so hiding the option is convenience, not the control. */}
              {myRole === "owner" && (
                <SelectItem value="owner">Owner — full access</SelectItem>
              )}
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="emp-pin">Terminal PIN</FieldLabel>
          <Input
            id="emp-pin"
            inputMode="numeric"
            maxLength={6}
            value={form.pin}
            onChange={(e) =>
              setForm({ ...form, pin: e.target.value.replace(/\D/g, "") })
            }
            className="numeric"
          />
          <FieldDescription>
            Optional. 4–6 digits, for switching cashiers mid-shift.
          </FieldDescription>
        </Field>
      </div>

      <DialogFooter>
        <Button variant="outline" onClick={onDone}>
          Cancel
        </Button>
        <Button
          onClick={() => create.mutate()}
          disabled={!canSave || create.isPending}
        >
          {create.isPending && <Loader2 className="size-4 animate-spin" />}
          Add employee
        </Button>
      </DialogFooter>
    </>
  );
}
