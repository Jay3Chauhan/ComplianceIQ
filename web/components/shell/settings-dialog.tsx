"use client";

import { useQueryClient } from "@tanstack/react-query";
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
import { useMeta } from "@/lib/queries";
import { useSettings } from "@/lib/settings";
import { useUI } from "@/lib/ui";

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

export function SettingsDialog() {
  const { settingsOpen, setSettingsOpen } = useUI();
  const settings = useSettings();
  const { theme, setTheme } = useTheme();
  const meta = useMeta();
  const qc = useQueryClient();
  const router = useRouter();
  const [confirm, setConfirm] = useState("");
  const [deleting, setDeleting] = useState(false);

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
      <DialogContent className="sm:max-w-lg">
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
          <Row label="Suggest follow-up questions" hint="Shows next questions under each answer.">
            <Switch checked={settings.followups} onCheckedChange={(followups) => settings.set({ followups })} />
          </Row>
          <Row label="Open sources automatically" hint="Shows the evidence panel when an answer cites documents.">
            <Switch checked={settings.showSources} onCheckedChange={(showSources) => settings.set({ showSources })} />
          </Row>
        </div>

        <Separator />
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
        {meta.data && (
          <p className="text-center text-[11px] text-muted-foreground">
            ComplianceIQ API v{meta.data.version} · answers by {String(meta.data.models.answer ?? "")}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
