import type { Metadata } from "next";
import { headers } from "next/headers";

import { ForgotPasswordForm } from "@/components/auth/forgot-password-form";

export const metadata: Metadata = { title: "Forgot password" };

export default async function ForgotPasswordPage() {
  const requestHeaders = await headers();
  return <ForgotPasswordForm tenantSlug={requestHeaders.get("x-tenant-slug")} />;
}
