"use client";

import { CheckIcon, CopyIcon, PencilIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { IconButton } from "@/components/common/icon-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface Props {
  content: string;
  editable: boolean;
  editing: boolean;
  laterMessages: number;
  onEditStart: () => void;
  onEditCancel: () => void;
  onEditSubmit: (question: string) => void;
}

export function UserMessage({ content, editable, editing, laterMessages, onEditStart, onEditCancel, onEditSubmit }: Props) {
  const [draft, setDraft] = useState(content);
  const [copied, setCopied] = useState(false);
  const [wasEditing, setWasEditing] = useState(editing);
  const ref = useRef<HTMLTextAreaElement>(null);

  if (editing !== wasEditing) {
    setWasEditing(editing);
    if (editing) setDraft(content);
  }

  useEffect(() => {
    if (!editing) return;
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
      el.style.height = "auto";
      el.style.height = `${el.scrollHeight}px`;
    });
  }, [editing]);

  const submit = () => {
    const q = draft.trim();
    if (q.length < 3) return;
    if (q === content.trim()) return onEditCancel();
    onEditSubmit(q);
  };

  if (editing) {
    return (
      <div className="ml-auto w-full max-w-[85%] animate-fade-up rounded-2xl border border-primary/40 bg-card p-3 shadow-sm ring-3 ring-primary/10">
        <textarea
          ref={ref}
          value={draft}
          maxLength={2000}
          rows={1}
          aria-label="Edit question"
          onChange={(e) => {
            setDraft(e.target.value);
            e.target.style.height = "auto";
            e.target.style.height = `${Math.min(e.target.scrollHeight, 240)}px`;
          }}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
            if (e.key === "Escape") {
              e.stopPropagation();
              onEditCancel();
            }
          }}
          className="w-full resize-none bg-transparent text-[15px] leading-7 outline-none"
        />
        <div className="mt-2 flex items-center gap-2">
          <p className="flex-1 text-xs text-muted-foreground">
            {laterMessages > 0
              ? `Sending removes the ${laterMessages} message${laterMessages === 1 ? "" : "s"} after this one.`
              : "Enter to send · Esc to cancel"}
          </p>
          <Button size="sm" variant="ghost" onClick={onEditCancel}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit} disabled={draft.trim().length < 3}>
            Save & send
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="group/user flex animate-fade-up flex-col items-end">
      <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary/[0.07] px-4 py-2.5 text-[15px] leading-7 whitespace-pre-wrap text-foreground ring-1 ring-primary/10 ring-inset dark:bg-primary/12">
        {content}
      </div>
      <div className={cn("mt-1 flex gap-0.5 opacity-0 transition-opacity group-hover/user:opacity-100 focus-within:opacity-100")}>
        <IconButton
          label={copied ? "Copied" : "Copy question"}
          size="icon-xs"
          onClick={async () => {
            await navigator.clipboard.writeText(content);
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          }}
        >
          {copied ? <CheckIcon /> : <CopyIcon />}
        </IconButton>
        {editable && (
          <IconButton label="Edit question" size="icon-xs" onClick={onEditStart}>
            <PencilIcon />
          </IconButton>
        )}
      </div>
    </div>
  );
}
