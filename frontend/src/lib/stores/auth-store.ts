"use client";

import { create } from "zustand";

import { clearAccessToken, setAccessToken } from "@/lib/api/token-store";
import type { SessionInfo, UserPublic, UserRole } from "@/lib/api/types";
import type { PermissionValue } from "@/lib/permissions";

interface AuthState {
  user: UserPublic | null;
  tenantSlug: string | null;
  permissions: Set<string>;
  /** False until the first refresh attempt settles, so guards can wait. */
  isReady: boolean;

  setSession: (session: SessionInfo) => void;
  setAccessToken: (token: string, expiresIn: number) => void;
  markReady: () => void;
  clear: () => void;

  can: (permission: PermissionValue) => boolean;
  canAny: (...permissions: PermissionValue[]) => boolean;
  hasRole: (...roles: UserRole[]) => boolean;
}

/**
 * Deliberately NOT persisted. The session is rebuilt on load from the
 * httpOnly refresh cookie, so there is nothing here worth writing to disk --
 * and a persisted copy of a user's role would just be a stale thing to
 * mistrust.
 */
export const useAuthStore = create<AuthState>((set, get) => ({
  user: null,
  tenantSlug: null,
  permissions: new Set<string>(),
  isReady: false,

  setSession: (session) =>
    set({
      user: session.user,
      tenantSlug: session.tenant_slug,
      permissions: new Set(session.permissions),
      isReady: true,
    }),

  setAccessToken: (token, expiresIn) => setAccessToken(token, expiresIn),

  markReady: () => set({ isReady: true }),

  clear: () => {
    clearAccessToken();
    set({ user: null, tenantSlug: null, permissions: new Set(), isReady: true });
  },

  can: (permission) => get().permissions.has(permission),
  canAny: (...permissions) => permissions.some((p) => get().permissions.has(p)),
  hasRole: (...roles) => {
    const role = get().user?.role;
    return role ? roles.includes(role) : false;
  },
}));

export const useCurrentUser = () => useAuthStore((s) => s.user);
export const useIsAuthenticated = () => useAuthStore((s) => s.user !== null);
export const useAuthReady = () => useAuthStore((s) => s.isReady);
