"use client";

import type { PermissionValue } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";

interface PermissionGateProps {
  children: React.ReactNode;
  /** Renders children only if the user holds every listed permission. */
  require: PermissionValue | PermissionValue[];
  fallback?: React.ReactNode;
}

/**
 * Hides UI the API would refuse anyway. The permission list comes from
 * /auth/me, so it always matches what the backend will actually allow.
 */
export function PermissionGate({
  children,
  require,
  fallback = null,
}: PermissionGateProps) {
  const permissions = useAuthStore((s) => s.permissions);
  const required = Array.isArray(require) ? require : [require];
  const allowed = required.every((permission) => permissions.has(permission));

  return <>{allowed ? children : fallback}</>;
}
