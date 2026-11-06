import type { Conversation, Source } from "@/lib/api/types";

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = (Date.now() - then) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function formatDate(value: string): string {
  if (!value) return "";
  const d = new Date(value);
  return Number.isNaN(d.getTime())
    ? value
    : d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export type ConversationGroup = { label: string; items: Conversation[] };

export function groupConversations(items: Conversation[]): ConversationGroup[] {
  if (!items.length) return [];
  const startOfToday = new Date();
  startOfToday.setHours(0, 0, 0, 0);
  const today = startOfToday.getTime();
  const day = 86400 * 1000;
  const buckets: [string, (t: number) => boolean][] = [
    ["Today", (t) => t >= today],
    ["Yesterday", (t) => t >= today - day],
    ["Previous 7 days", (t) => t >= today - 7 * day],
    ["Previous 30 days", (t) => t >= today - 30 * day],
    ["Older", () => true],
  ];
  const groups: ConversationGroup[] = [];
  const pinned = items.filter((c) => c.pinned);
  if (pinned.length) groups.push({ label: "Pinned", items: pinned });
  for (const c of items.filter((c) => !c.pinned)) {
    const t = new Date(c.updated_at).getTime();
    const label = buckets.find(([, test]) => test(t))![0];
    const group = groups.find((g) => g.label === label);
    if (group) group.items.push(c);
    else groups.push({ label, items: [c] });
  }
  return groups;
}

export function shortDocName(name: string): string {
  return name
    .replace(/^RBI Master Direction on /i, "RBI MD · ")
    .replace(/^SEBI Master Circular for /i, "SEBI MC · ")
    .replace(/^RBI Guidelines on /i, "RBI · ")
    .replace(/^ReBIT Account Aggregator /i, "ReBIT AA · ");
}

export function answerToClipboard(answer: string, sources: Source[]): string {
  if (!sources.length) return answer;
  const lines = sources.map(
    (s) =>
      `[${s.id}] ${s.doc_name}${s.circular_id ? `, ${s.circular_id}` : ""}${s.section ? `, ${s.section}` : ""}, page ${s.page_number}`,
  );
  return `${answer}\n\nSources\n${lines.join("\n")}`;
}

export function categoryLabel(category: string): string {
  return { ALL: "All regulators", RBI: "RBI", SEBI: "SEBI", AA: "Account Aggregator" }[category] ?? category;
}
