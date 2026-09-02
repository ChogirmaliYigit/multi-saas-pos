"use client";

import { AuthGuard } from "@/components/auth/auth-guard";

/**
 * The terminal gets no sidebar, no page padding and no scroll.
 *
 * A checkout screen is a fixed-viewport application, not a document: the
 * product grid and the cart each scroll independently, and the page itself
 * never does. Managers and owners can open it too, so they can cover a till.
 */
export default function PosLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard roles={["cashier", "manager", "owner"]}>
      <div className="bg-muted/40 fixed inset-0 flex flex-col overflow-hidden">
        {children}
      </div>
    </AuthGuard>
  );
}
