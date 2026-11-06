"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  ArchiveIcon,
  ArchiveRestoreIcon,
  DownloadIcon,
  MoreHorizontalIcon,
  PencilIcon,
  PinIcon,
  PinOffIcon,
  Trash2Icon,
} from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Conversation } from "@/lib/api/types";
import { runForConversation, useChatStore } from "@/lib/chat/store";
import { downloadConversation } from "@/lib/export";
import { useDeleteConversation, useUpdateConversation } from "@/lib/queries";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

export function ConversationRow({ conversation, active }: { conversation: Conversation; active: boolean }) {
  const router = useRouter();
  const update = useUpdateConversation();
  const remove = useDeleteConversation();
  const streaming = useChatStore(runForConversation(conversation.id)) !== null;
  const setMobileNavOpen = useUI((s) => s.setMobileNavOpen);
  const [renaming, setRenaming] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [title, setTitle] = useState(conversation.title);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (renaming) requestAnimationFrame(() => inputRef.current?.select());
  }, [renaming]);

  const startRename = () => {
    setTitle(conversation.title);
    setRenaming(true);
  };

  const commitRename = () => {
    const next = title.trim();
    setRenaming(false);
    if (next && next !== conversation.title) update.mutate({ id: conversation.id, patch: { title: next } });
  };

  const onDelete = () => {
    remove.mutate(conversation.id, {
      onSuccess: () => {
        if (active) router.push("/");
      },
    });
  };

  if (renaming) {
    return (
      <div className="px-1 py-0.5">
        <input
          ref={inputRef}
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === "Enter") commitRename();
            if (e.key === "Escape") setRenaming(false);
          }}
          aria-label="Conversation title"
          className="h-8 w-full rounded-md border border-primary/50 bg-background px-2 text-sm outline-none ring-3 ring-primary/15"
        />
      </div>
    );
  }

  return (
    <>
      <div
        className={cn(
          "group/row relative flex items-center rounded-lg text-sm transition-colors",
          active
            ? "bg-sidebar-accent text-sidebar-accent-foreground"
            : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
        )}
      >
        <Link
          href={`/c/${conversation.id}`}
          onClick={() => setMobileNavOpen(false)}
          onDoubleClick={startRename}
          className="flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-8 pl-2.5"
          aria-current={active ? "page" : undefined}
        >
          {streaming && (
            <span className="relative flex size-2 shrink-0" aria-label="Generating">
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-primary opacity-60" />
              <span className="relative inline-flex size-2 rounded-full bg-primary" />
            </span>
          )}
          {conversation.pinned && !streaming && <PinIcon className="size-3 shrink-0 text-muted-foreground" />}
          <span className="truncate">{conversation.title}</span>
        </Link>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              aria-label={`Options for ${conversation.title}`}
              className="absolute right-1 flex size-6 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity group-hover/row:opacity-100 hover:bg-background/80 hover:text-foreground focus-visible:opacity-100 data-[state=open]:opacity-100"
            >
              <MoreHorizontalIcon className="size-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-48">
            <DropdownMenuItem onSelect={startRename}>
              <PencilIcon /> Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => update.mutate({ id: conversation.id, patch: { pinned: !conversation.pinned } })}
            >
              {conversation.pinned ? <PinOffIcon /> : <PinIcon />} {conversation.pinned ? "Unpin" : "Pin"}
            </DropdownMenuItem>
            <DropdownMenuSub>
              <DropdownMenuSubTrigger>
                <DownloadIcon /> Export
              </DropdownMenuSubTrigger>
              <DropdownMenuSubContent>
                <DropdownMenuItem onSelect={() => downloadConversation(conversation.id, "markdown")}>
                  Markdown (.md)
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => downloadConversation(conversation.id, "json")}>
                  JSON (.json)
                </DropdownMenuItem>
              </DropdownMenuSubContent>
            </DropdownMenuSub>
            <DropdownMenuItem
              onSelect={() => update.mutate({ id: conversation.id, patch: { archived: !conversation.archived } })}
            >
              {conversation.archived ? <ArchiveRestoreIcon /> : <ArchiveIcon />}
              {conversation.archived ? "Unarchive" : "Archive"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirmDelete(true)}>
              <Trash2Icon /> Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              “{conversation.title}” and all its answers will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={onDelete}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
