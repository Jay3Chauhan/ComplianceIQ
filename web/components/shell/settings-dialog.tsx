"use client";

import { useQueryClient } from "@tanstack/react-query";
import { KeyboardIcon, ShieldCheckIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { api, errorMessage } from "@/lib/api/client";
import type { AnswerMode, Category } from "@/lib/api/types";
import { useAdminSession } from "@/lib/admin-queries";
import { useMeta, useReady } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { useUI } from "@/lib/ui";
import { cn } from "@/lib/utils";

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-6 py-3">
      <div className="min-w-0">
        <Label className="text-sm font-medium">{label}</Label>
        {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

const FEATURE_LABELS: Record<string, string> = {
  rerank: "Cross-encoder rerank",
  query_rewrite: "Follow-up rewriting",
  verification: "Answer verification",
  llm_verifier: "LLM claim check",
  answer_repair: "Answer repair",
  followups: "Follow-up suggestions",
  llm_titles: "AI titles",
};

function modelName(value: unknown): string {
  return typeof value === "string" ? value.split("/").pop()! : "";
}

function AboutSection({ open }: { open: boolean }) {
  const meta = useMeta();
  const ready = useReady(open);
  const admin = useAdminSession();
  const { setSettingsOpen, setShortcutsOpen } = useUI();
  const m = meta.data;
  return (
    <section className="space-y-3 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium">About and status</p>
        {ready.data ? (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium",
              ready.data.status === "ready" ? "bg-verified/12 text-verified" : "bg-partial/15 text-partial",
            )}
            title={Object.entries(ready.data.checks)
              .map(([k, c]) => `${k}: ${c.ok ? "ok" : c.detail}`)
              .join("\n")}
          >
            <span className="size-1.5 rounded-full bg-current" />
            {ready.data.status === "ready" ? "All systems ready" : "Degraded"}
          </span>
        ) : ready.isError ? (
          <span className="rounded-full bg-unverified/12 px-2 py-0.5 text-[11px] font-medium text-unverified">API unreachable</span>
        ) : null}
      </div>
      {m && (
        <>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-xs">
            <dt className="text-muted-foreground">API</dt>
            <dd>v{m.version}</dd>
            <dt className="text-muted-foreground">Answers</dt>
            <dd className="truncate font-mono">{modelName(m.models.answer)}</dd>
            <dt className="text-muted-foreground">Rewrite / verify</dt>
            <dd className="truncate font-mono">{modelName(m.models.fast)}</dd>
            <dt className="text-muted-foreground">Retrieval</dt>
            <dd className="truncate font-mono">
              {modelName(m.models.embedding)}
              {m.models.reranker ? ` + ${modelName(m.models.reranker)}` : ""} · {String(m.features.retrieval_strategy ?? "")}
            </dd>
          </dl>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(FEATURE_LABELS).map(([key, label]) => {
              const on = m.features[key] === true;
              return (
                <span
                  key={key}
                  className={cn(
                    "rounded-md px-1.5 py-0.5 text-[11px]",
                    on ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground line-through",
                  )}
                >
                  {label}
                </span>
              );
            })}
          </div>
        </>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          className="h-7"
          onClick={() => {
            setSettingsOpen(false);
            setShortcutsOpen(true);
          }}
        >
          <KeyboardIcon /> Shortcuts
        </Button>
        {admin.data?.enabled && (
          <Button asChild variant="outline" size="sm" className="h-7">
            <Link href="/admin" onClick={() => setSettingsOpen(false)}>
              <ShieldCheckIcon /> Admin console
            </Link>
          </Button>
        )}
      </div>
    </section>
  );
}

export function SettingsDialog() {
  const { settingsOpen, setSettingsOpen } = useUI();
  const settings = useSettings();
  const { theme, setTheme } = useTheme();
  const meta = useMeta();
  const qc = useQueryClient();
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);
  const followupsAvailable = meta.data?.features.followups !== false;

  const deleteAll = async () => {
    setDeleting(true);
    try {
      const { deleted } = await api<{ deleted: number }>("conversations", { method: "DELETE" });
      qc.removeQueries({ queryKey: ["conversation"] });
      await qc.invalidateQueries({ queryKey: ["conversations"] });
      toast.success(`Deleted ${deleted} conversation${deleted === 1 ? "" : "s"}.`);
      setConfirm("");
      setSettingsOpen(false);
      router.push("/");
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>Preferences are saved in this browser.</DialogDescription>
        </DialogHeader>

        <div className="divide-y divide-border">
          <Row label="Theme">
            <Select value={theme ?? "system"} onValueChange={setTheme}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="system">System</SelectItem>
                <SelectItem value="light">Light</SelectItem>
                <SelectItem value="dark">Dark</SelectItem>
              </SelectContent>
            </Select>
          </Row>
          <Row label="Default regulator" hint="New chats start with this filter.">
            <Select value={settings.category} onValueChange={(v) => settings.set({ category: v as Category })}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(meta.data?.categories ?? [{ id: "ALL", label: "All regulators" }]).map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row label="Default answer mode" hint="Auto cites documents when they cover the question.">
            <Select value={settings.answerMode} onValueChange={(v) => settings.set({ answerMode: v as AnswerMode })}>
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(meta.data?.answer_modes ?? [{ id: "auto", label: "Auto" }]).map((m) => (
                  <SelectItem key={m.id} value={m.id}>
                    {m.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Row>
          <Row
            label="Suggest follow-up questions"
            hint={followupsAvailable ? "Shows next questions under each answer." : "Turned off on this server."}
          >
            <Switch
              checked={followupsAvailable && settings.followups}
              disabled={!followupsAvailable}
              onCheckedChange={(followups) => settings.set({ followups })}
            />
          </Row>
          <Row label="Open sources automatically" hint="Shows the evidence panel when an answer cites documents.">
            <Switch checked={settings.showSources} onCheckedChange={(showSources) => settings.set({ showSources })} />
          </Row>
        </div>

        <Separator />
        <AboutSection open={settingsOpen} />
        <div className="space-y-3 rounded-lg border border-destructive/30 bg-destructive/5 p-4">
          <div>
            <p className="text-sm font-medium text-destructive">Delete all conversations</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Permanently removes every conversation in this browser’s history. Type <b>delete</b> to confirm.
            </p>
          </div>
          <div className="flex gap-2">
            <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="delete" className="h-8" />
            <Button
              variant="destructive"
              size="sm"
              className="h-8"
              disabled={confirm.trim().toLowerCase() !== "delete" || deleting}
              onClick={deleteAll}
            >
              Delete all
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
