"use client";

import { MoonIcon, SunIcon } from "lucide-react";
import { useTheme } from "next-themes";
import { IconButton } from "@/components/common/icon-button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  // The resolved theme is unknown on the server, so the label stays theme-neutral.
  return (
    <IconButton label="Toggle theme" onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}>
      <SunIcon className="hidden dark:block" />
      <MoonIcon className="dark:hidden" />
    </IconButton>
  );
}
