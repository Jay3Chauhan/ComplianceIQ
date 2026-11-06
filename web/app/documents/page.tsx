import type { Metadata } from "next";
import { Library } from "@/components/documents/library";

export const metadata: Metadata = { title: "Library" };

export default function DocumentsPage() {
  return <Library />;
}
