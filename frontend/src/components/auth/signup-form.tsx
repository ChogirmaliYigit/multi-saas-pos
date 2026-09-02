"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { Loader2 } from "lucide-react";
import Link from "next/link";
import { useEffect } from "react";
import { useForm, useWatch } from "react-hook-form";
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
import {
  Field,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { env } from "@/lib/env";
import { useSignup } from "@/lib/hooks/use-auth";

const RESERVED = ["www", "api", "admin", "app", "static", "assets", "mail"];

// Mirrors the backend validators, so the user sees the problem before a round
// trip. The server still re-validates -- this is convenience, not trust.
const schema = z.object({
  shop_name: z.string().min(2, "Shop name is too short").max(160),
  slug: z
    .string()
    .min(3, "At least 3 characters")
    .max(63)
    .regex(
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/,
      "Lowercase letters, numbers and hyphens only",
    )
    .refine((value) => !RESERVED.includes(value), "That address is reserved"),
  owner_name: z.string().min(2, "Enter your name").max(160),
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(10, "Use at least 10 characters").max(128),
  currency: z.string().length(3),
  country_code: z.string().length(2),
});

type SignupValues = z.infer<typeof schema>;

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}

export function SignupForm() {
  const signup = useSignup();

  const form = useForm<SignupValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      shop_name: "",
      slug: "",
      owner_name: "",
      email: "",
      password: "",
      currency: "USD",
      country_code: "US",
    },
  });

  // useWatch subscribes to a single field; form.watch() re-renders on every
  // keystroke anywhere in the form and cannot be memoized by React Compiler.
  const shopName = useWatch({ control: form.control, name: "shop_name" });
  const slug = useWatch({ control: form.control, name: "slug" });
  const slugDirty = form.formState.dirtyFields.slug;

  // Suggest the address from the shop name until the user edits it themselves.
  useEffect(() => {
    if (!slugDirty) {
      form.setValue("slug", slugify(shopName), { shouldValidate: false });
    }
  }, [shopName, slugDirty, form]);

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle className="text-xl">Create your shop</CardTitle>
        <CardDescription>Starts a free trial. No card required.</CardDescription>
      </CardHeader>

      <form onSubmit={form.handleSubmit((values) => signup.mutate(values))}>
        <CardContent>
          <FieldGroup>
            <Field data-invalid={!!form.formState.errors.shop_name}>
              <FieldLabel htmlFor="shop_name">Shop name</FieldLabel>
              <Input id="shop_name" autoFocus {...form.register("shop_name")} />
              <FieldError errors={[form.formState.errors.shop_name]} />
            </Field>

            <Field data-invalid={!!form.formState.errors.slug}>
              <FieldLabel htmlFor="slug">Shop address</FieldLabel>
              <Input id="slug" {...form.register("slug")} />
              <FieldDescription>
                {slug || "your-shop"}.{env.baseDomain}
              </FieldDescription>
              <FieldError errors={[form.formState.errors.slug]} />
            </Field>

            <Field data-invalid={!!form.formState.errors.owner_name}>
              <FieldLabel htmlFor="owner_name">Your name</FieldLabel>
              <Input
                id="owner_name"
                autoComplete="name"
                {...form.register("owner_name")}
              />
              <FieldError errors={[form.formState.errors.owner_name]} />
            </Field>

            <Field data-invalid={!!form.formState.errors.email}>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                {...form.register("email")}
              />
              <FieldError errors={[form.formState.errors.email]} />
            </Field>

            <Field data-invalid={!!form.formState.errors.password}>
              <FieldLabel htmlFor="password">Password</FieldLabel>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                {...form.register("password")}
              />
              <FieldDescription>At least 10 characters.</FieldDescription>
              <FieldError errors={[form.formState.errors.password]} />
            </Field>

            <div className="grid grid-cols-2 gap-4">
              <Field data-invalid={!!form.formState.errors.currency}>
                <FieldLabel htmlFor="currency">Currency</FieldLabel>
                <Input
                  id="currency"
                  maxLength={3}
                  className="uppercase"
                  {...form.register("currency")}
                />
                <FieldError errors={[form.formState.errors.currency]} />
              </Field>
              <Field data-invalid={!!form.formState.errors.country_code}>
                <FieldLabel htmlFor="country_code">Country</FieldLabel>
                <Input
                  id="country_code"
                  maxLength={2}
                  className="uppercase"
                  {...form.register("country_code")}
                />
                <FieldError errors={[form.formState.errors.country_code]} />
              </Field>
            </div>
          </FieldGroup>
        </CardContent>

        <CardFooter className="mt-6 flex-col gap-3">
          <Button type="submit" className="w-full" disabled={signup.isPending}>
            {signup.isPending && <Loader2 className="size-4 animate-spin" />}
            Create shop
          </Button>
          <p className="text-muted-foreground text-center text-sm">
            Already have a shop?{" "}
            <Link
              href="/login"
              className="text-foreground underline underline-offset-4"
            >
              Sign in
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
