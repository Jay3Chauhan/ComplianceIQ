import { cn } from "@/lib/utils";

const STYLES: Record<string, string> = {
  RBI: "bg-rbi/12 text-rbi ring-rbi/25",
  SEBI: "bg-sebi/12 text-sebi ring-sebi/25",
  AA: "bg-aa/12 text-aa ring-aa/25",
};

export function regulatorColor(category: string): string {
  return { RBI: "var(--rbi)", SEBI: "var(--sebi)", AA: "var(--aa)" }[category] ?? "var(--muted-foreground)";
}

export function RegulatorBadge({ category, className }: { category: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center rounded-md px-1.5 font-mono text-[10.5px] font-semibold tracking-wide ring-1 ring-inset",
        STYLES[category] ?? "bg-muted text-muted-foreground ring-border",
        className,
      )}
    >
      {category || "DOC"}
    </span>
  );
}
