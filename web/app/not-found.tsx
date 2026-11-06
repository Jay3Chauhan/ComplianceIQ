import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 px-4 text-center">
      <p className="font-mono text-sm text-muted-foreground">404</p>
      <h1 className="text-xl font-semibold">This page doesn’t exist</h1>
      <Button asChild className="mt-2">
        <Link href="/">Back to chat</Link>
      </Button>
    </div>
  );
}
