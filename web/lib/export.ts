export type ExportFormat = "markdown" | "json";

/** The BFF forwards Content-Disposition, so a plain link download keeps the server's filename. */
export function downloadConversation(conversationId: string, format: ExportFormat) {
  const a = document.createElement("a");
  a.href = `/api/conversations/${conversationId}/export?format=${format}`;
  a.rel = "noopener";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}
