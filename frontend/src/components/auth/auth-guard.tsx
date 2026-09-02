"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import type { UserRole } from "@/lib/api/types";
import { ROLE_HOME } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

interface AuthGuardProps {
  children: React.ReactNode;
  /** When set, a signed-in user outside these roles is sent to their own home. */
  roles?: UserRole[];
}

/**
 * Client-side gate. This is UX, not security: it decides what to *render*
 * while the API independently rejects anything the user may not do. Every
 * protected screen fetches from the API, and those calls are authorised
 * server-side regardless of what this component does.
 */
export function AuthGuard({ children, roles }: AuthGuardProps) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const isReady = useAuthStore((s) => s.isReady);

  useEffect(() => {
    if (!isReady) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    if (roles && !roles.includes(user.role)) {
      router.replace(ROLE_HOME[user.role]);
    }
  }, [isReady, user, roles, router]);

  // `isReady` is what stops a hard reload flashing the login screen before
  // the refresh-cookie handshake has had a chance to run.
  if (!isReady || !user || (roles && !roles.includes(user.role))) {
    return <AuthGuardSkeleton />;
  }

  return <>{children}</>;
}

function AuthGuardSkeleton() {
  return (
    <div className="flex h-dvh w-full items-center justify-center p-8">
      <div className="w-full max-w-md space-y-4">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}
