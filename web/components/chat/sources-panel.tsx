"use client";

import { BookOpenCheckIcon, XIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { SourceCard } from "@/components/chat/source-card";
import { IconButton } from "@/components/common/icon-button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/lib/use-media-query";
import { useUI } from "@/lib/ui";

function PanelBody({ onClose }: { onClose: () => void }) {
  const selection = useUI((s) => s.selection);
  const refs = useRef<Map<number, HTMLDivElement>>(new Map());

  useEffect(() => {
    if (selection?.highlight) {
      refs.current.get(selection.highlight)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selection?.highlight, selection?.nonce]);

  const sources = selection?.sources ?? [];
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border px-4">
        <BookOpenCheckIcon className="size-4 text-primary" />
        <h2 className="text-sm font-semibold">Sources</h2>
        {sources.length > 0 && (
          <span className="rounded-full bg-muted px-1.5 font-mono text-[11px] text-muted-foreground">{sources.length}</span>
        )}
        <IconButton label="Close sources" className="ml-auto" onClick={onClose}>
          <XIcon />
        </IconButton>
      </div>
      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-4">
          {sources.length === 0 ? (
            <div className="px-4 py-16 text-center">
              <BookOpenCheckIcon className="mx-auto size-8 text-muted-foreground/50" />
              <p className="mt-3 text-sm font-medium">No sources selected</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Click a citation like <span className="font-mono text-primary">[1]</span> in an answer to see the exact
                passage it came from.
              </p>
            </div>
          ) : (
            sources.map((s) => (
              <SourceCard
                key={s.chunk_id}
                ref={(el) => {
                  if (el) refs.current.set(s.id, el);
                  else refs.current.delete(s.id);
                }}
                source={s}
                highlighted={selection?.highlight === s.id}
                flashKey={selection?.highlight === s.id ? selection.nonce : undefined}
              />
            ))
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

/** Evidence panel: a docked column on wide screens, a sheet on smaller ones. */
export function SourcesPanel() {
  const { sourcesOpen, setSourcesOpen } = useUI();
  const wide = useMediaQuery("(min-width: 1280px)");
  const close = () => setSourcesOpen(false);

  if (wide) {
    return sourcesOpen ? (
      <aside className="w-[380px] shrink-0 animate-in border-l border-border bg-background fade-in-0 slide-in-from-right-4">
        <PanelBody onClose={close} />
      </aside>
    ) : null;
  }
  return (
    <Sheet open={sourcesOpen} onOpenChange={setSourcesOpen}>
      <SheetContent side="right" className="w-[92vw] gap-0 p-0 sm:max-w-md" showCloseButton={false}>
        <SheetTitle className="sr-only">Sources</SheetTitle>
        <PanelBody onClose={close} />
      </SheetContent>
    </Sheet>
  );
}
