"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, KeyRound, Loader2, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/layout/page-header";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { authApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { initials } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

export default function AccountPage() {
  const user = useAuthStore((s) => s.user);

  if (!user) {
    return <Skeleton className="h-96 w-full" />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Account"
        description="Your profile, password and terminal PIN."
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <ProfileCard />
        <div className="space-y-4">
          <PasswordCard />
          <PinCard />
        </div>
      </div>
    </div>
  );
}

function ProfileCard() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user)!;
  const setUser = useAuthStore((s) => s.setUser);

  const [form, setForm] = useState({
    full_name: user.full_name,
    phone: user.phone ?? "",
    avatar_url: user.avatar_url ?? "",
  });

  const save = useMutation({
    mutationFn: () =>
      authApi.updateProfile({
        full_name: form.full_name.trim(),
        phone: form.phone.trim() || null,
        avatar_url: form.avatar_url.trim() || null,
      }),
    onSuccess: async (updated) => {
      // Update the store directly so the sidebar avatar changes immediately
      // rather than after the next session refetch.
      setUser(updated);
      await queryClient.invalidateQueries({ queryKey: ["session"] });
      toast.success("Profile updated.");
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not save your profile.",
      ),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>
          How you appear to colleagues on the terminal and in reports.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-4">
          <Avatar className="size-14">
            {form.avatar_url && <AvatarImage src={form.avatar_url} alt="" />}
            <AvatarFallback>{initials(form.full_name || "?")}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <p className="truncate font-medium">{user.email}</p>
            <Badge variant="secondary" className="mt-1">
              {ROLE_LABEL[user.role]}
            </Badge>
          </div>
        </div>

        <Field>
          <FieldLabel htmlFor="acc-name">Full name</FieldLabel>
          <Input
            id="acc-name"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="acc-phone">Phone</FieldLabel>
          <Input
            id="acc-phone"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
        </Field>

        <Field>
          <FieldLabel htmlFor="acc-avatar">Avatar URL</FieldLabel>
          <Input
            id="acc-avatar"
            value={form.avatar_url}
            placeholder="https://…"
            onChange={(e) => setForm({ ...form, avatar_url: e.target.value })}
          />
          <FieldDescription>
            Shown on the PIN picker, so cashiers can find themselves at a glance.
          </FieldDescription>
        </Field>

        <FieldDescription>
          Your role and branch are set by an owner, not here.
        </FieldDescription>

        <div className="flex justify-end">
          <Button
            onClick={() => save.mutate()}
            disabled={form.full_name.trim().length < 2 || save.isPending}
          >
            {save.isPending && <Loader2 className="size-4 animate-spin" />}
            Save profile
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");

  const change = useMutation({
    mutationFn: () => authApi.changePassword(current, next),
    onSuccess: (result) => {
      setCurrent("");
      setNext("");
      setConfirm("");
      toast.success(result.message, { duration: 7000 });
    },
    onError: (error) =>
      toast.error(
        isApiError(error) ? error.message : "Could not change the password.",
      ),
  });

  const mismatch = confirm.length > 0 && next !== confirm;
  const canSave = current && next.length >= 10 && next === confirm;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="size-4" /> Password
        </CardTitle>
        <CardDescription>
          Changing it signs you out everywhere else — that is the point of changing
          it after a suspected compromise.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Field>
          <FieldLabel htmlFor="pw-current">Current password</FieldLabel>
          <Input
            id="pw-current"
            type="password"
            autoComplete="current-password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="pw-new">New password</FieldLabel>
          <Input
            id="pw-new"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
          />
          <FieldDescription>
            At least 10 characters.{" "}
            {next.length >= 10 && <Check className="text-primary inline size-3" />}
          </FieldDescription>
        </Field>
        <Field data-invalid={mismatch || undefined}>
          <FieldLabel htmlFor="pw-confirm">Confirm new password</FieldLabel>
          <Input
            id="pw-confirm"
            type="password"
            autoComplete="new-password"
            aria-invalid={mismatch}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
          {mismatch && (
            <FieldDescription className="text-destructive">
              The two passwords do not match.
            </FieldDescription>
          )}
        </Field>

        <div className="flex justify-end">
          <Button
            onClick={() => change.mutate()}
            disabled={!canSave || change.isPending}
          >
            {change.isPending && <Loader2 className="size-4 animate-spin" />}
            Change password
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function PinCard() {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");

  const save = useMutation({
    mutationFn: () => authApi.setPin(pin),
    onSuccess: (result) => {
      setPin("");
      setConfirm("");
      toast.success(result.message);
    },
    onError: (error) =>
      toast.error(isApiError(error) ? error.message : "Could not set the PIN."),
  });

  const digitsOnly = (value: string) => value.replace(/\D/g, "");
  const mismatch = confirm.length > 0 && pin !== confirm;
  const canSave = pin.length >= 4 && pin.length <= 6 && pin === confirm;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <KeyRound className="size-4" /> Terminal PIN
        </CardTitle>
        <CardDescription>
          For switching cashiers mid-shift without typing an email and password at a
          busy till.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field>
            <FieldLabel htmlFor="pin-new">New PIN</FieldLabel>
            <Input
              id="pin-new"
              inputMode="numeric"
              maxLength={6}
              autoComplete="off"
              className="numeric tracking-[0.4em]"
              value={pin}
              onChange={(e) => setPin(digitsOnly(e.target.value))}
            />
          </Field>
          <Field data-invalid={mismatch || undefined}>
            <FieldLabel htmlFor="pin-confirm">Confirm PIN</FieldLabel>
            <Input
              id="pin-confirm"
              inputMode="numeric"
              maxLength={6}
              autoComplete="off"
              aria-invalid={mismatch}
              className="numeric tracking-[0.4em]"
              value={confirm}
              onChange={(e) => setConfirm(digitsOnly(e.target.value))}
            />
          </Field>
        </div>
        <FieldDescription>
          4–6 digits. A PIN unlocks the till, never the admin panel.
        </FieldDescription>

        <div className="flex justify-end">
          <Button
            onClick={() => save.mutate()}
            disabled={!canSave || save.isPending}
          >
            {save.isPending && <Loader2 className="size-4 animate-spin" />}
            Set PIN
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
