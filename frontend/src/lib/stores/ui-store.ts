"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

interface UiState {
  sidebarCollapsed: boolean;
  /** Branch the admin panel is currently looking at; null means "all". */
  activeBranchId: string | null;

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setActiveBranch: (branchId: string | null) => void;
}

/**
 * Persisted, unlike auth state: these are display preferences, and a shop
 * owner expects their collapsed sidebar to stay collapsed. Nothing here is
 * sensitive or authoritative.
 */
export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      activeBranchId: null,

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setActiveBranch: (activeBranchId) => set({ activeBranchId }),
    }),
    { name: "pos-ui-preferences" },
  ),
);
