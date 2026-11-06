"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { ArrowUpIcon, CheckIcon, ChevronDownIcon, FileCheck2Icon, LayersIcon, SparklesIcon, SquareIcon, WandSparklesIcon } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import type { AnswerMode, Category } from "@/lib/api/types";
import { useMeta } from "@/lib/queries";
import { cn } from "@/lib/utils";

const MAX = 2000;

const CATEGORY_FALLBACK = [
  { id: "ALL", label: "All regulators", description: "Search every loaded document" },
  { id: "RBI", label: "RBI", description: "Reserve Bank of India master directions and circulars" },
  { id: "SEBI", label: "SEBI", description: "SEBI master circulars" },
  { id: "AA", label: "Account Aggregator", description: "NBFC-AA directions and ReBIT specifications" },
];
const MODE_FALLBACK = [
  { id: "auto", label: "Auto", description: "Cited answer when the documents cover it, otherwise a labelled general answer" },
  { id: "regulatory", label: "Documents only", description: "Only answers from loaded documents" },
  { id: "general", label: "General knowledge", description: "Answers without document citations" },
];
const MODE_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  auto: WandSparklesIcon,
  regulatory: FileCheck2Icon,
  general: SparklesIcon,
};
const DOT: Record<string, string> = { ALL: "bg-primary", RBI: "bg-rbi", SEBI: "bg-sebi", AA: "bg-aa" };

export interface ComposerHandle {
  focus: () => void;
  setValue: (value: string) => void;
}

interface Props {
  busy: boolean;
  stopping: boolean;
  category: Category;
  answerMode: AnswerMode;
  onCategory: (c: Category) => void;
  onAnswerMode: (m: AnswerMode) => void;
  onSend: (question: string) => Promise<boolean>;
  onStop: () => void;
  onEditLast?: () => void;
  autoFocus?: boolean;
  placeholder?: string;
}

export const Composer = forwardRef<ComposerHandle, Props>(function Composer(
  { busy, stopping, category, answerMode, onCategory, onAnswerMode, onSend, onStop, onEditLast, autoFocus, placeholder },
  handle,
) {
  const meta = useMeta();
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const categories = meta.data?.categories ?? CATEGORY_FALLBACK;
  const modes = meta.data?.answer_modes ?? MODE_FALLBACK;
  const currentCategory = categories.find((c) => c.id === category) ?? categories[0];
  const currentMode = modes.find((m) => m.id === answerMode) ?? modes[0];
  const ModeIcon = MODE_ICON[answerMode] ?? WandSparklesIcon;
  const trimmed = value.trim();
  const canSend = !busy && trimmed.length >= 3 && trimmed.length <= MAX;

  const resize = () => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 224)}px`;
  };

  useImperativeHandle(handle, () => ({
    focus: () => ref.current?.focus(),
    setValue: (v) => {
      setValue(v);
      requestAnimationFrame(() => {
        resize();
        ref.current?.focus();
      });
    },
  }));

  useEffect(() => {
    if (autoFocus && window.matchMedia("(pointer: fine)").matches) ref.current?.focus();
  }, [autoFocus]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const typing = target.closest("input, textarea, [contenteditable=true]");
      if (e.key === "/" && !typing) {
        e.preventDefault();
        ref.current?.focus();
      }
      if (e.key === "Escape" && busy && !target.closest("[role=dialog]")) onStop();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onStop]);

  const submit = async () => {
    if (!canSend) return;
    const question = trimmed;
    setValue("");
    requestAnimationFrame(resize);
    const ok = await onSend(question);
    if (!ok) {
      setValue(question);
      requestAnimationFrame(resize);
    }
  };

  return (
    <div className="w-full">
      <div
        className={cn(
          "relative rounded-2xl border border-border bg-card shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.12)] transition-[border-color,box-shadow] focus-within:border-primary/40 focus-within:ring-4 focus-within:ring-primary/8 dark:shadow-none",
        )}
      >
        <textarea
          ref={ref}
          value={value}
          rows={1}
          maxLength={MAX + 200}
          aria-label="Ask a compliance question"
          placeholder={placeholder ?? "Ask a compliance question…"}
          onChange={(e) => {
            setValue(e.target.value);
            resize();
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void submit();
            } else if (e.key === "ArrowUp" && !value && onEditLast) {
              e.preventDefault();
              onEditLast();
            }
          }}
          className="block max-h-56 min-h-[52px] w-full resize-none bg-transparent px-4 pt-3.5 pb-1 text-[15px] leading-6 outline-none placeholder:text-muted-foreground/80"
        />
        <div className="flex items-center gap-1 px-2 pb-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[state=open]:bg-muted">
                <span className={cn("size-2 rounded-full", DOT[category] ?? "bg-primary")} />
                <span className="max-w-28 truncate sm:max-w-none">{currentCategory?.label}</span>
                <ChevronDownIcon className="size-3.5 opacity-60" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-72">
              <DropdownMenuLabel className="text-xs text-muted-foreground">Search in</DropdownMenuLabel>
              {categories.map((c) => (
                <DropdownMenuItem key={c.id} onSelect={() => onCategory(c.id as Category)} className="items-start gap-2.5 py-2">
                  <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", DOT[c.id] ?? "bg-primary")} />
                  <span className="flex-1">
                    <span className="block text-sm font-medium">{c.label}</span>
                    <span className="block text-xs text-muted-foreground">{c.description}</span>
                  </span>
                  {c.id === category && <CheckIcon className="mt-1 text-primary" />}
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button className="inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-[13px] text-muted-foreground transition-colors hover:bg-muted hover:text-foreground data-[state=open]:bg-muted">
                <ModeIcon className="size-3.5" />
                <span className="hidden sm:inline">{currentMode?.label}</span>
                <ChevronDownIcon className="size-3.5 opacity-60" />
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="start" className="w-80">
              <DropdownMenuLabel className="text-xs text-muted-foreground">Answer mode</DropdownMenuLabel>
              {modes.map((m) => {
                const Icon = MODE_ICON[m.id] ?? LayersIcon;
                return (
                  <DropdownMenuItem key={m.id} onSelect={() => onAnswerMode(m.id as AnswerMode)} className="items-start gap-2.5 py-2">
                    <Icon className="mt-0.5 text-muted-foreground" />
                    <span className="flex-1">
                      <span className="block text-sm font-medium">{m.label}</span>
                      <span className="block text-xs text-muted-foreground">{m.description}</span>
                    </span>
                    {m.id === answerMode && <CheckIcon className="mt-0.5 text-primary" />}
                  </DropdownMenuItem>
                );
              })}
            </DropdownMenuContent>
          </DropdownMenu>

          <div className="ml-auto flex items-center gap-2">
            {value.length > MAX * 0.8 && (
              <span className={cn("font-mono text-[11px]", value.length > MAX ? "text-destructive" : "text-muted-foreground")}>
                {value.length}/{MAX}
              </span>
            )}
            {busy ? (
              <Tooltip>
                <TooltipTrigger asChild>
                  <button
                    onClick={onStop}
                    disabled={stopping}
                    aria-label="Stop generating"
                    className="flex size-8 items-center justify-center rounded-full bg-foreground text-background transition-transform hover:scale-105 disabled:opacity-50"
                  >
                    <SquareIcon className="size-3 fill-current" />
                  </button>
                </TooltipTrigger>
                <TooltipContent>Stop (Esc)</TooltipContent>
              </Tooltip>
            ) : (
              <button
                onClick={() => void submit()}
                disabled={!canSend}
                aria-label="Send"
                className="flex size-8 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-sm transition-all hover:scale-105 disabled:scale-100 disabled:bg-muted disabled:text-muted-foreground disabled:shadow-none"
              >
                <ArrowUpIcon className="size-4" strokeWidth={2.5} />
              </button>
            )}
          </div>
        </div>
      </div>
      <p className="mt-2 text-center text-[11px] text-muted-foreground/80">
        Answers cite the loaded RBI, SEBI and AA documents and are fact-checked — but they aren’t legal advice.
      </p>
    </div>
  );
});
