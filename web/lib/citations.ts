const CITE = /\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)(?:,\s*p\.?\s*\d+)?\](?!\()/g;

function expand(group: string): number[] {
  return group.split(/\s*,\s*/).flatMap((part) => {
    const [a, b] = part.split(/\s*[–-]\s*/).map(Number);
    if (!b || b < a || b - a > 20) return [a];
    return Array.from({ length: b - a + 1 }, (_, i) => a + i);
  });
}

/**
 * Turns `[1]`, `[1, 2]`, `[1-3]` and `[2, p.34]` into markdown links `#cite-n` that the
 * markdown renderer swaps for citation chips. Code spans and fenced blocks are left alone.
 */
export function linkCitations(markdown: string): string {
  return markdown
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) =>
      i % 2 === 1
        ? part
        : part.replace(CITE, (_m, group: string) => expand(group).map((n) => `[${n}](#cite-${n})`).join("")),
    )
    .join("");
}

export function citedNumbers(markdown: string): Set<number> {
  const out = new Set<number>();
  for (const m of markdown.matchAll(CITE)) expand(m[1]).forEach((n) => out.add(n));
  return out;
}
