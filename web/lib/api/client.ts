export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public retryAfter?: number,
    public requestId?: string | null,
  ) {
    super(message);
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  const body = await res.json().catch(() => null);
  const err = body?.error;
  return new ApiError(
    res.status,
    err?.code ?? "error",
    err?.message ?? (res.status === 502 ? "The ComplianceIQ API is not reachable." : res.statusText || "Request failed"),
    Number(res.headers.get("retry-after")) || undefined,
    err?.request_id,
  );
}

type Init = { method?: string; body?: unknown; signal?: AbortSignal };

/** Browser → BFF (/api/*). JSON or FormData bodies. Throws ApiError with the backend's error code. */
export async function api<T>(path: string, init: Init = {}): Promise<T> {
  const isForm = init.body instanceof FormData;
  const res = await fetch(`/api/${path.replace(/^\/+/, "")}`, {
    method: init.method ?? (init.body !== undefined ? "POST" : "GET"),
    headers: init.body !== undefined && !isForm ? { "Content-Type": "application/json" } : undefined,
    body: init.body === undefined ? undefined : isForm ? (init.body as FormData) : JSON.stringify(init.body),
    signal: init.signal,
  });
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 429) return `You're asking quickly — try again in ${err.retryAfter ?? 30}s.`;
    if (err.code === "llm_unavailable") return "The assistant is temporarily busy. Try again in a minute.";
    return err.message;
  }
  return err instanceof Error ? err.message : "Something went wrong.";
}
