"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Source } from "@/lib/api/types";

export interface SourcesSelection {
  /** Message id (or run id while streaming) the sources belong to. */
  owner: string;
  sources: Source[];
  highlight: number | null;
  /** Bumped on every citation click so the same chip can re-trigger the flash. */
  nonce: number;
}

interface UIState {
  sidebarCollapsed: boolean;
  mobileNavOpen: boolean;
  settingsOpen: boolean;
  sourcesOpen: boolean;
  selection: SourcesSelection | null;
  setSidebarCollapsed: (v: boolean) => void;
  setMobileNavOpen: (v: boolean) => void;
  setSettingsOpen: (v: boolean) => void;
  setSourcesOpen: (v: boolean) => void;
  showSources: (owner: string, sources: Source[], highlight?: number | null) => void;
  /** Keeps the panel in sync with the latest answer without opening it. */
  syncSources: (owner: string, sources: Source[]) => void;
}

export const useUI = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      mobileNavOpen: false,
      settingsOpen: false,
      sourcesOpen: false,
      selection: null,
      setSidebarCollapsed: (sidebarCollapsed) => set({ sidebarCollapsed }),
      setMobileNavOpen: (mobileNavOpen) => set({ mobileNavOpen }),
      setSettingsOpen: (settingsOpen) => set({ settingsOpen }),
      setSourcesOpen: (sourcesOpen) => set({ sourcesOpen }),
      showSources: (owner, sources, highlight = null) =>
        set((s) => ({
          sourcesOpen: true,
          selection: { owner, sources, highlight, nonce: (s.selection?.nonce ?? 0) + 1 },
        })),
      syncSources: (owner, sources) =>
        set((s) =>
          s.selection?.owner === owner && s.selection.sources === sources
            ? s
            : { selection: { owner, sources, highlight: null, nonce: s.selection?.nonce ?? 0 } },
        ),
    }),
    {
      name: "complianceiq-ui",
      partialize: (s) => ({ sidebarCollapsed: s.sidebarCollapsed }),
      skipHydration: true,
    },
  ),
);
