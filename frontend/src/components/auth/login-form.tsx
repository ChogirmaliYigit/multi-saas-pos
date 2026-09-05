"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Field, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { useLogin } from "@/lib/hooks/use-auth";

const schema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
  tenant_slug: z.string().optional(),
});

type LoginValues = z.infer<typeof schema>;

export function LoginForm({ tenantSlug }: { tenantSlug: string | null }) {
  const login = useLogin();

  const form = useForm<LoginValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", tenant_slug: tenantSlug ?? "" },
  });

  const onSubmit = (values: LoginValues) =>
    login.mutate({
      email: values.email,
      password: values.password,
      // On a tenant subdomain the backend resolves the shop from the Host, so
      // the field is only shown (and sent) when there is no subdomain.
      tenant_slug: tenantSlug ?? values.tenant_slug ?? null,
    });

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-xl">Sign in</CardTitle>
        <CardDescription>
          {tenantSlug
            ? `Signing in to ${tenantSlug}`
            : "Enter your shop address and credentials."}
        </CardDescription>
      </CardHeader>

      <form onSubmit={form.handleSubmit(onSubmit)}>
        <CardContent>
          <FieldGroup>
            {!tenantSlug && (
              <Field data-invalid={!!form.formState.errors.tenant_slug}>
                <FieldLabel htmlFor="tenant_slug">Shop address</FieldLabel>
                <Input
                  id="tenant_slug"
                  placeholder="corner-store"
                  autoComplete="organization"
                  {...form.register("tenant_slug")}
                />
              </Field>
            )}

            <Field data-invalid={!!form.formState.errors.email}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                autoFocus
                {...form.register("email")}
              />
              <FieldError errors={[form.formState.errors.email]} />
            </Field>

            <Field data-invalid={!!form.formState.errors.password}>
              <div className="flex items-baseline justify-between">
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Link
                  href="/forgot-password"
                  className="text-muted-foreground hover:text-foreground text-xs underline underline-offset-4"
                >
                  Forgot?
                </Link>
              </div>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...form.register("password")}
              />
              <FieldError errors={[form.formState.errors.password]} />
            </Field>
          </FieldGroup>
        </CardContent>

        <CardFooter className="mt-6 flex-col gap-3">
          <Button type="submit" className="w-full" disabled={login.isPending}>
            {login.isPending && <Loader2 className="size-4 animate-spin" />}
            Sign in
          </Button>
          <p className="text-muted-foreground text-center text-sm">
            New here?{" "}
            <Link
              href="/signup"
              className="text-foreground underline underline-offset-4"
            >
              Create a shop
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
