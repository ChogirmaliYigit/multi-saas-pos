"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";

import { authApi } from "@/lib/api/endpoints";
import { getAccessToken, setAccessToken } from "@/lib/api/token-store";
import { useAuthStore } from "@/lib/stores/auth-store";

export const sessionQueryKey = ["session"] as const;

/**
 * Rebuilds the session after a page load.
 *
 * The access token lives in memory, so a refresh wipes it. This first tries
 * `/api/auth/refresh` (which reads the httpOnly cookie), and only then asks
 * the API who the user is. `isReady` flips either way, so route guards can
 * tell "not signed in" apart from "not checked yet" -- without that
 * distinction, every reload flashes the login screen.
 */
export function useSessionBootstrap() {
  const setSession = useAuthStore((s) => s.setSession);
  const markReady = useAuthStore((s) => s.markReady);
  const clear = useAuthStore((s) => s.clear);

  const query = useQuery({
    queryKey: sessionQueryKey,
    queryFn: async () => {
      if (!getAccessToken()) {
        const response = await fetch("/api/auth/refresh", {
          method: "POST",
          credentials: "same-origin",
        });
        if (!response.ok) return null;
        const data = await response.json();
        setAccessToken(data.access_token, data.expires_in);
      }
      return authApi.session();
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
  });

  useEffect(() => {
    if (query.isPending) return;
    if (query.data) {
      setSession(query.data);
    } else if (query.isError || query.data === null) {
      clear();
    }
    markReady();
  }, [query.data, query.isError, query.isPending, setSession, clear, markReady]);

  return query;
}
