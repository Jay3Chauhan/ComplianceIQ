"use client";

import { ThumbsDownIcon, ThumbsUpIcon } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { IconButton } from "@/components/common/icon-button";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Popover, PopoverAnchor, PopoverContent } from "@/components/ui/popover";
import { Textarea } from "@/components/ui/textarea";
import { FEEDBACK_REASONS, type Feedback } from "@/lib/api/types";
import { useFeedback } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function FeedbackBar({
  conversationId,
  messageId,
  feedback,
}: {
  conversationId: string;
  messageId: string;
  feedback: Feedback | null;
}) {
  const mutation = useFeedback(conversationId, messageId);
  const [open, setOpen] = useState(false);
  const [reasons, setReasons] = useState<string[]>(feedback?.rating === -1 ? feedback.reasons : []);
  const [comment, setComment] = useState(feedback?.comment ?? "");
  const rating = feedback?.rating ?? 0;

  const up = () => mutation.mutate(rating === 1 ? null : { rating: 1, reasons: [], comment: null });
  const down = () => {
    if (rating === -1) mutation.mutate(null);
    else setOpen(true);
  };
  const submit = () => {
    mutation.mutate(
      { rating: -1, reasons, comment: comment.trim() || null },
      { onSuccess: () => toast.success("Thanks — this helps improve answers.") },
    );
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverAnchor asChild>
        <span className="inline-flex">
          <IconButton label={rating === 1 ? "Remove rating" : "Helpful"} onClick={up}>
            <ThumbsUpIcon className={cn(rating === 1 && "fill-verified/25 text-verified")} />
          </IconButton>
          <IconButton label={rating === -1 ? "Remove rating" : "Not helpful"} onClick={down}>
            <ThumbsDownIcon className={cn(rating === -1 && "fill-unverified/20 text-unverified")} />
          </IconButton>
        </span>
      </PopoverAnchor>
      <PopoverContent align="start" className="w-80">
        <p className="text-sm font-semibold">What went wrong?</p>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {FEEDBACK_REASONS.map((r) => (
            <label key={r.id} className="flex cursor-pointer items-center gap-2 text-xs">
              <Checkbox
                checked={reasons.includes(r.id)}
                onCheckedChange={(v) => setReasons((prev) => (v ? [...prev, r.id] : prev.filter((x) => x !== r.id)))}
              />
              {r.label}
            </label>
          ))}
        </div>
        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Optional details (e.g. the correct page)"
          maxLength={2000}
          className="mt-3 min-h-16 text-sm"
        />
        <div className="mt-3 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={submit}>
            Send feedback
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
