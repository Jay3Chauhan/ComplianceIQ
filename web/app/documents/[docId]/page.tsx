import { Suspense } from "react";
import { DocumentReader } from "@/components/documents/reader";

export default function DocumentPage({ params }: PageProps<"/documents/[docId]">) {
  return (
    <Suspense>
      <Reader params={params} />
    </Suspense>
  );
}

async function Reader({ params }: Pick<PageProps<"/documents/[docId]">, "params">) {
  const { docId } = await params;
  return <DocumentReader docId={decodeURIComponent(docId)} />;
}
