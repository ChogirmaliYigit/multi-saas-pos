"use client";

import Link from "next/link";

import { AuthGuard } from "@/components/auth/auth-guard";
import { PermissionGate } from "@/components/auth/permission-gate";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { AppTopbar } from "@/components/layout/app-topbar";
import { PageTransition } from "@/components/motion/page-transition";
import { Button } from "@/components/ui/button";
import { shopNavigation, posEntry } from "@/lib/navigation";
import { Permission } from "@/lib/permissions";

/**
 * Tenant admin shell. Cashiers are redirected to /pos by AuthGuard -- the
 * admin panel is not a place they should land by typing a URL.
 */
export default function ShopLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard roles={["owner", "manager"]}>
      <div className="flex h-dvh overflow-hidden">
        <AppSidebar
          sections={shopNavigation}
          footer={
            <PermissionGate require={Permission.ORDER_CREATE}>
              <Button
                asChild
                size="sm"
                variant="secondary"
                className="w-full gap-2"
              >
                <Link href={posEntry.href}>
                  <posEntry.icon className="size-4" />
                  <span className="truncate">Terminal</span>
                </Link>
              </Button>
            </PermissionGate>
          }
        />
        <div className="flex min-w-0 flex-1 flex-col">
          <AppTopbar sections={shopNavigation} />
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
