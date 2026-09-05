"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, MailCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { authApi } from "@/lib/api/endpoints";

export function ForgotPasswordForm({ tenantSlug }: { tenantSlug: string | null }) {
  const [email, setEmail] = useState("");
  const [shop, setShop] = useState("");
  const [sent, setSent] = useState(false);

  const request = useMutation({
    mutationFn: () => authApi.forgotPassword(email, tenantSlug ?? shop ?? null),
    // Success either way. The API deliberately answers the same whether or
    // not the address has an account, and showing an error here would leak
    // exactly what the API refuses to.
    onSettled: () => setSent(true),
  });

  if (sent) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="bg-primary/10 text-primary mb-2 flex size-11 items-center justify-center rounded-xl">
            <MailCheck className="size-5" />
          </div>
          <CardTitle className="text-xl">Check your email</CardTitle>
          <CardDescription>
            If {email} has an account, a reset link is on its way. It expires in an
            hour and works once.
          </CardDescription>
        </CardHeader>
        <CardFooter className="flex-col gap-3">
          <Button asChild variant="outline" className="w-full">
            <Link href="/login">Back to sign in</Link>
          </Button>
          <button
            type="button"
            onClick={() => setSent(false)}
            className="text-muted-foreground text-sm underline underline-offset-4"
          >
            Use a different address
          </button>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Forgot your password?</CardTitle>
        <CardDescription>
          We&apos;ll email you a link to choose a new one.
        </CardDescription>
      </CardHeader>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          request.mutate();
        }}
      >
        <CardContent className="space-y-4">
          {!tenantSlug && (
            <Field>
              <FieldLabel htmlFor="shop">Shop address</FieldLabel>
              <Input
                id="shop"
                value={shop}
                onChange={(event) => setShop(event.target.value)}
                placeholder="corner-store"
                autoComplete="organization"
              />
              <FieldDescription>
                Leave blank if you are a platform operator.
              </FieldDescription>
            </Field>
          )}

          <Field>
            <FieldLabel htmlFor="email">Email</FieldLabel>
            <Input
              id="email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
              autoFocus
            />
          </Field>
        </CardContent>

        <CardFooter className="mt-6 flex-col gap-3">
          <Button
            type="submit"
            className="w-full"
            disabled={!email.trim() || request.isPending}
          >
            {request.isPending && <Loader2 className="size-4 animate-spin" />}
            Send reset link
          </Button>
          <Link
            href="/login"
            className="text-muted-foreground text-sm underline underline-offset-4"
          >
            Back to sign in
          </Link>
        </CardFooter>
      </form>
    </Card>
  );
}
