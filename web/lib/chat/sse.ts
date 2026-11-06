import { toApiError } from "@/lib/api/client";
import type { StreamEvent } from "@/lib/api/types";

/**
 * POSTs to a BFF streaming route and yields parsed SSE events.
 * Non-2xx responses (404, 409 conversation_busy, 422, 429) throw ApiError before any event.
 * `onActivity` fires for every frame, heartbeats included, to feed a stall watchdog.
 */
export async function* streamSSE(
  path: string,
  body: unknown,
  signal: AbortSignal,
  onActivity?: () => void,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`/api/${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body ?? {}),
    signal,
  });
  if (!res.ok || !res.body) throw await toApiError(res);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value.replace(/\r\n/g, "\n");
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        onActivity?.();
        const data = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n");
        if (!data || data === "[DONE]") continue;
        try {
          yield JSON.parse(data) as StreamEvent;
        } catch {
          // ignore a malformed frame rather than failing the whole answer
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
