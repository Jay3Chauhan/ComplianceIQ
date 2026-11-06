"use client";

import { memo, useMemo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationChip } from "@/components/chat/citation-chip";
import type { Source } from "@/lib/api/types";
import { linkCitations } from "@/lib/citations";
import { cn } from "@/lib/utils";

interface Props {
  text: string;
  sources: Source[];
  onCite: (n: number) => void;
  streaming?: boolean;
  className?: string;
}

export const AnswerMarkdown = memo(function AnswerMarkdown({ text, sources, onCite, streaming, className }: Props) {
  const components = useMemo<Components>(
    () => ({
      a: ({ href, children }) => {
        const cite = href?.match(/^#cite-(\d+)$/);
        if (cite) {
          const n = Number(cite[1]);
          return <CitationChip n={n} source={sources.find((s) => s.id === n)} onCite={onCite} />;
        }
        return (
          <a href={href} target="_blank" rel="noopener noreferrer">
            {children}
          </a>
        );
      },
      table: ({ children }) => (
        <div className="my-4 overflow-x-auto rounded-lg border border-border">
          <table className="!my-0">{children}</table>
        </div>
      ),
    }),
    [sources, onCite],
  );

  return (
    <div
      className={cn(
        "prose-answer",
        streaming &&
          "[&>:is(p,h1,h2,h3,h4,blockquote):last-child]:streaming-caret [&>:is(ul,ol):last-child>li:last-child]:streaming-caret",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {linkCitations(text)}
      </ReactMarkdown>
    </div>
  );
});
