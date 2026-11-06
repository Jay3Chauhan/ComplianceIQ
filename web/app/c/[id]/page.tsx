import { Suspense } from "react";
import { ChatView, ConversationSkeleton } from "@/components/chat/chat-view";

export default function ConversationPage({ params }: PageProps<"/c/[id]">) {
  return (
    <Suspense
      fallback={
        <div className="mx-auto w-full max-w-3xl px-4 pt-20">
          <ConversationSkeleton />
        </div>
      }
    >
      <Conversation params={params} />
    </Suspense>
  );
}

async function Conversation({ params }: Pick<PageProps<"/c/[id]">, "params">) {
  const { id } = await params;
  return <ChatView key={id} conversationId={id} />;
}
