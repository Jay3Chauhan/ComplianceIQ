import {
  BookOpenIcon,
  CircleStopIcon,
  Loader2Icon,
  MessageSquareTextIcon,
  PenLineIcon,
  SearchIcon,
  ShieldQuestionIcon,
  Wand2Icon,
} from "lucide-react";
import type { AnswerStage } from "@/lib/chat/reducer";

const ICONS: Partial<Record<AnswerStage, React.ComponentType<{ className?: string }>>> = {
  understanding: MessageSquareTextIcon,
  searching: SearchIcon,
  thinking: BookOpenIcon,
  writing: PenLineIcon,
  verifying: ShieldQuestionIcon,
  revising: Wand2Icon,
};

export function StatusLine({ stage, text, stopping }: { stage: AnswerStage; text: string; stopping?: boolean }) {
  const Icon = stopping ? CircleStopIcon : (ICONS[stage] ?? Loader2Icon);
  return (
    <div className="flex items-center gap-2 text-[13px] text-muted-foreground" role="status" aria-live="polite">
      <span className="relative flex size-5 items-center justify-center">
        <span className="absolute inset-0 animate-ping rounded-full bg-primary/15 [animation-duration:1.6s]" />
        <Icon className={stage === "starting" && !stopping ? "size-3.5 animate-spin" : "size-3.5 text-primary"} />
      </span>
      <span className="animate-pulse [animation-duration:2s]">{stopping ? "Stopping…" : text}</span>
    </div>
  );
}
