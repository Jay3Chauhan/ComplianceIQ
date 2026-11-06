"use client";

import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useUI } from "@/lib/ui";

const GROUPS: { title: string; items: { keys: string[]; label: string }[] }[] = [
  {
    title: "General",
    items: [
      { keys: ["Ctrl", "Shift", "O"], label: "New chat" },
      { keys: ["Ctrl", "K"], label: "Search conversations" },
      { keys: ["?"], label: "Show keyboard shortcuts" },
    ],
  },
  {
    title: "Composer",
    items: [
      { keys: ["/"], label: "Focus the message box" },
      { keys: ["Enter"], label: "Send" },
      { keys: ["Shift", "Enter"], label: "New line" },
      { keys: ["↑"], label: "Edit your last message (empty box)" },
      { keys: ["Esc"], label: "Stop generating" },
    ],
  },
];

export function ShortcutsDialog() {
  const { shortcutsOpen, setShortcutsOpen } = useUI();
  return (
    <Dialog open={shortcutsOpen} onOpenChange={setShortcutsOpen}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Keyboard shortcuts</DialogTitle>
          <DialogDescription>Use ⌘ instead of Ctrl on macOS.</DialogDescription>
        </DialogHeader>
        <div className="space-y-5">
          {GROUPS.map((g) => (
            <section key={g.title}>
              <h3 className="mb-1.5 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">{g.title}</h3>
              <ul className="divide-y divide-border">
                {g.items.map((item) => (
                  <li key={item.label} className="flex items-center justify-between gap-4 py-2 text-sm">
                    <span>{item.label}</span>
                    <span className="flex gap-1">
                      {item.keys.map((k) => (
                        <kbd
                          key={k}
                          className="inline-flex h-6 min-w-6 items-center justify-center rounded-md border border-border bg-muted px-1.5 font-mono text-[11px] text-muted-foreground"
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}
