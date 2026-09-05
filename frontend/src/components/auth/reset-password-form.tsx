"use client";

import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Loader2, ShieldAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { authApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";

export function ResetPasswordForm({ token }: { token: string | null }) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [done, setDone] = useState(false);

  const reset = useMutation({
    mutationFn: () => authApi.resetPassword(token!, password),
    onSuccess: () => setDone(true),
  });

  // A link with no token is a mangled email, not a user mistake.
  if (!token) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="bg-destructive/10 text-destructive mb-2 flex size-11 items-center justify-center rounded-xl">
            <ShieldAlert className="size-5" />
          </div>
          <CardTitle className="text-xl">This link is incomplete</CardTitle>
          <CardDescription>
            Open the link from your email exactly as it was sent, or request a new
            one.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button asChild className="w-full">
            <Link href="/forgot-password">Request a new link</Link>
          </Button>
        </CardFooter>
      </Card>
    );
  }

  if (done) {
    return (
      <Card className="w-full max-w-sm">
        <CardHeader>
          <div className="bg-primary/10 text-primary mb-2 flex size-11 items-center justify-center rounded-xl">
            <CheckCircle2 className="size-5" />
          </div>
          <CardTitle className="text-xl">Password updated</CardTitle>
          <CardDescription>
            Everywhere else you were signed in has been signed out.
          </CardDescription>
        </CardHeader>
        <CardFooter>
          <Button className="w-full" onClick={() => router.replace("/login")}>
            Sign in
          </Button>
        </CardFooter>
      </Card>
    );
  }

  const tooShort = password.length > 0 && password.length < 10;
  const mismatch = confirm.length > 0 && confirm !== password;
  const canSubmit = password.length >= 10 && confirm === password;

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Choose a new password</CardTitle>
        <CardDescription>
          This link works once. Signing in elsewhere will require the new password.
        </CardDescription>
      </CardHeader>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          reset.mutate();
        }}
      >
        <CardContent className="space-y-4">
          <Field data-invalid={tooShort}>
            <FieldLabel htmlFor="password">New password</FieldLabel>
            <Input
              id="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              autoFocus
            />
            <FieldDescription>At least 10 characters.</FieldDescription>
            {tooShort && (
              <FieldError errors={[{ message: "Use at least 10 characters" }]} />
            )}
          </Field>

          <Field data-invalid={mismatch}>
            <FieldLabel htmlFor="confirm">Confirm</FieldLabel>
            <Input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(event) => setConfirm(event.target.value)}
              autoComplete="new-password"
            />
            {mismatch && (
              <FieldError errors={[{ message: "These do not match" }]} />
            )}
          </Field>

          {reset.isError && (
            <p className="text-destructive text-sm">
              {isApiError(reset.error)
                ? reset.error.message
                : "Could not reset the password."}
              {isApiError(reset.error) &&
                reset.error.code === "invalid_reset_token" && (
                  <>
                    {" "}
                    <Link
                      href="/forgot-password"
                      className="underline underline-offset-4"
                    >
                      Request a new link
                    </Link>
                    .
                  </>
                )}
            </p>
          )}
        </CardContent>

        <CardFooter className="mt-6">
          <Button
            type="submit"
            className="w-full"
            disabled={!canSubmit || reset.isPending}
          >
            {reset.isPending && <Loader2 className="size-4 animate-spin" />}
            Update password
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
