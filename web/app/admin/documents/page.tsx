import type { Metadata } from "next";
import { DocumentsManager } from "@/components/admin/documents-manager";

export const metadata: Metadata = { title: "Admin · Documents", robots: { index: false } };

export default function AdminDocumentsPage() {
  return <DocumentsManager />;
}
