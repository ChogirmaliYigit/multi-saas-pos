"use client";

import { AuthGuard } from "@/components/auth/auth-guard";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppTopbar } from "@/components/layout/app-topbar";
import { PageTransition } from "@/components/motion/page-transition";
import { platformNavigation } from "@/lib/navigation";

/** SaaS operator shell. Separate route group so it never inherits shop chrome. */
export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard roles={["super_admin"]}>
      <div className="flex h-dvh overflow-hidden">
        <AppSidebar
          sections={platformNavigation}
          title="POS Platform"
          subtitle="Operator console"
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <AppTopbar sections={platformNavigation} showPosLink={false} />
          <main className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-7xl p-4 sm:p-6">
              <PageTransition>{children}</PageTransition>
            </div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
