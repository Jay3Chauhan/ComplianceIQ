"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AnswerMode, Category } from "@/lib/api/types";

interface Settings {
  category: Category;
  answerMode: AnswerMode;
  followups: boolean;
  showSources: boolean;
  set: (patch: Partial<Omit<Settings, "set">>) => void;
}

/** User preferences, stored in localStorage. New chats start from these defaults. */
export const useSettings = create<Settings>()(
  persist(
    (set) => ({
      category: "ALL",
      answerMode: "auto",
      followups: true,
      showSources: true,
      set: (patch) => set(patch),
    }),
    // Rehydrated after mount (see Providers) so server and first client render agree.
    { name: "complianceiq-settings", version: 1, skipHydration: true },
  ),
);
