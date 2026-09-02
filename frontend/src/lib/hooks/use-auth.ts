"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { sessionApi } from "@/lib/api/endpoints";
import { isApiError } from "@/lib/api/errors";
import { setAccessToken } from "@/lib/api/token-store";
import { ROLE_HOME } from "@/lib/permissions";
import { useAuthStore } from "@/lib/stores/auth-store";
import { sessionQueryKey } from "./use-session";

export function useLogin() {
  const queryClient = useQueryClient();
  const router = useRouter();

  return useMutation({
    mutationFn: sessionApi.login,
    onSuccess: async (data) => {
      setAccessToken(data.access_token, data.expires_in);
      // Refetch rather than trust the login response: /auth/me is the single
      // source of truth for role and permissions.
      const session = await queryClient.fetchQuery({
        queryKey: sessionQueryKey,
        queryFn: async () => {
          const { authApi } = await import("@/lib/api/endpoints");
          return authApi.session();
        },
      });
      if (session) {
        useAuthStore.getState().setSession(session);
        router.replace(ROLE_HOME[session.user.role]);
      }
    },
    onError: (error) => {
      toast.error(
        isApiError(error) ? error.message : "Could not sign in. Try again.",
      );
    },
  });
}

export function useSignup() {
  const router = useRouter();
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: sessionApi.signup,
    onSuccess: async (data) => {
      if (data.access_token && data.expires_in) {
        setAccessToken(data.access_token, data.expires_in);
        await queryClient.invalidateQueries({ queryKey: sessionQueryKey });
        toast.success("Shop created. Welcome aboard.");
        router.replace("/dashboard");
        return;
      }
      toast.success("Shop created. Please sign in.");
      router.replace("/login");
    },
    onError: (error) => {
      toast.error(isApiError(error) ? error.message : "Could not create the shop.");
    },
  });
}

export function useLogout() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const clear = useAuthStore((s) => s.clear);

  return useMutation({
    mutationFn: sessionApi.logout,
    // Clear locally even if the network call fails -- the user asked to be
    // signed out, and leaving them looking signed in is the worse outcome.
    onSettled: () => {
      clear();
      queryClient.clear();
      router.replace("/login");
    },
  });
}
