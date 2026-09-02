import type { Metadata } from "next";
import { headers } from "next/headers";

import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = { title: "Sign in" };

export default async function LoginPage() {
  // Set by middleware from the Host header, so the shop is known before the
  // form renders and the address field can be skipped entirely.
  const requestHeaders = await headers();
  const tenantSlug = requestHeaders.get("x-tenant-slug");

  return <LoginForm tenantSlug={tenantSlug} />;
}
