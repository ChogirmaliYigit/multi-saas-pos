"use client";

import { useSessionBootstrap } from "@/lib/hooks/use-session";

/**
 * Runs the one-time session rebuild for the whole app. Rendered inside
 * QueryProvider, above every route group.
 */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  useSessionBootstrap();
  return <>{children}</>;
}
