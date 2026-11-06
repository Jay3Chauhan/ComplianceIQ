"use client";

import { useRef, useState } from "react";
import { FileUpIcon, FileTextIcon, Loader2Icon, XIcon } from "lucide-react";
import { toast } from "sonner";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError, errorMessage } from "@/lib/api/client";
import type { DocumentCategory, DocumentMetadata, DocumentSummary } from "@/lib/api/types";
import { useDeleteDocument, useUpdateDocument, useUploadDocument } from "@/lib/admin-queries";
import { useMeta } from "@/lib/queries";
import { cn } from "@/lib/utils";

const CATEGORIES: { id: DocumentCategory; label: string; issuer: string }[] = [
  { id: "RBI", label: "RBI", issuer: "Reserve Bank of India" },
  { id: "SEBI", label: "SEBI", issuer: "Securities and Exchange Board of India" },
  { id: "AA", label: "Account Aggregator", issuer: "Reserve Bank of India" },
  { id: "GENERAL", label: "General", issuer: "" },
];

const EMPTY: DocumentMetadata = { name: "", circular_id: "", category: "RBI", subcategory: "", date: "", issuer: "Reserve Bank of India", url: "" };

function nameFromFile(filename: string) {
  return filename
    .replace(/\.pdf$/i, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function Field({ label, htmlFor, hint, className, children }: { label: string; htmlFor: string; hint?: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={htmlFor} className="text-xs font-medium">
        {label}
      </Label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function MetadataFields({ value, onChange }: { value: DocumentMetadata; onChange: (v: DocumentMetadata) => void }) {
  const set = (patch: Partial<DocumentMetadata>) => onChange({ ...value, ...patch });
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <Field label="Title" htmlFor="doc-name" className="sm:col-span-2">
        <Input id="doc-name" required minLength={3} maxLength={200} value={value.name} onChange={(e) => set({ name: e.target.value })} />
      </Field>
      <Field label="Regulator" htmlFor="doc-category">
        <Select
          value={value.category}
          onValueChange={(v) => {
            const next = CATEGORIES.find((c) => c.id === v)!;
            const prevIssuer = CATEGORIES.find((c) => c.id === value.category)?.issuer;
            set({ category: next.id, issuer: !value.issuer || value.issuer === prevIssuer ? next.issuer : value.issuer });
          }}
        >
          <SelectTrigger id="doc-category" className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CATEGORIES.map((c) => (
              <SelectItem key={c.id} value={c.id}>
                {c.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <Field label="Topic" htmlFor="doc-sub">
        <Input id="doc-sub" placeholder="e.g. KYC" maxLength={120} value={value.subcategory} onChange={(e) => set({ subcategory: e.target.value })} />
      </Field>
      <Field label="Circular ID" htmlFor="doc-circular" className="sm:col-span-2">
        <Input
          id="doc-circular"
          className="font-mono text-xs"
          placeholder="RBI/2022-23/111"
          maxLength={120}
          value={value.circular_id}
          onChange={(e) => set({ circular_id: e.target.value })}
        />
      </Field>
      <Field label="Issued on" htmlFor="doc-date">
        <Input id="doc-date" type="date" value={value.date} onChange={(e) => set({ date: e.target.value })} />
      </Field>
      <Field label="Issuer" htmlFor="doc-issuer">
        <Input id="doc-issuer" maxLength={200} value={value.issuer} onChange={(e) => set({ issuer: e.target.value })} />
      </Field>
      <Field label="Official URL" htmlFor="doc-url" className="sm:col-span-2" hint="Shown as “View source” on citations.">
        <Input id="doc-url" type="url" placeholder="https://www.rbi.org.in/…" maxLength={500} value={value.url} onChange={(e) => set({ url: e.target.value })} />
      </Field>
    </div>
  );
}

export function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const meta = useMeta();
  const upload = useUploadDocument();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [form, setForm] = useState<DocumentMetadata>(EMPTY);
  const [replace, setReplace] = useState(false);
  const [exists, setExists] = useState(false);
  const [dragging, setDragging] = useState(false);
  const maxMb = meta.data?.limits.max_upload_mb ?? 50;

  const reset = () => {
    setFile(null);
    setForm(EMPTY);
    setReplace(false);
    setExists(false);
    upload.reset();
  };

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") return toast.error("Only PDF files can be indexed.");
    if (f.size > maxMb * 1024 * 1024) return toast.error(`That file is larger than ${maxMb} MB.`);
    setFile(f);
    setExists(false);
    setReplace(false);
    if (!form.name) setForm((v) => ({ ...v, name: nameFromFile(f.name) }));
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    upload.mutate(
      { file, meta: form, replace },
      {
        onSuccess: ({ document }) => {
          toast.success(`Uploaded ${document.name}`, { description: "Indexing has started. Progress shows under Jobs." });
          reset();
          onOpenChange(false);
        },
        onError: (err) => {
          if (err instanceof ApiError && err.code === "document_exists") setExists(true);
          else toast.error(errorMessage(err));
        },
      },
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (upload.isPending) return;
        if (!o) reset();
        onOpenChange(o);
      }}
    >
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Add a document</DialogTitle>
          <DialogDescription>The PDF is parsed, chunked and embedded in the background. Citations use this metadata.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {file ? (
            <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/40 p-3">
              <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <FileTextIcon className="size-5" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{file.name}</p>
                <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(1)} MB</p>
              </div>
              <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove file" disabled={upload.isPending} onClick={() => setFile(null)}>
                <XIcon />
              </Button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                pick(e.dataTransfer.files[0]);
              }}
              className={cn(
                "flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed p-8 text-center transition-colors",
                dragging ? "border-primary bg-primary/5" : "border-border hover:border-foreground/25 hover:bg-muted/40",
              )}
            >
              <FileUpIcon className="size-7 text-muted-foreground" />
              <span className="text-sm font-medium">Drop a PDF here or click to browse</span>
              <span className="text-xs text-muted-foreground">Up to {maxMb} MB · text-based PDFs (scanned images aren’t OCR’d)</span>
            </button>
          )}
          <input ref={input} type="file" accept="application/pdf,.pdf" hidden onChange={(e) => pick(e.target.files?.[0] ?? undefined)} />

          <MetadataFields value={form} onChange={setForm} />

          {exists && (
            <label className="flex items-start gap-2.5 rounded-lg border border-partial/40 bg-partial/8 p-3 text-sm">
              <Checkbox checked={replace} onCheckedChange={(v) => setReplace(v === true)} className="mt-0.5" />
              <span>
                <span className="font-medium">A document with this filename already exists.</span>
                <span className="block text-xs text-muted-foreground">Replace its file, metadata and passages.</span>
              </span>
            </label>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" disabled={upload.isPending} onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!file || form.name.trim().length < 3 || upload.isPending || (exists && !replace)}>
              {upload.isPending && <Loader2Icon className="animate-spin" />}
              {upload.isPending ? "Uploading…" : exists ? "Replace and index" : "Upload and index"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function toMetadata(doc: DocumentSummary): DocumentMetadata {
  return {
    name: doc.name,
    circular_id: doc.circular_id,
    category: (["RBI", "SEBI", "AA", "GENERAL"].includes(doc.category) ? doc.category : "GENERAL") as DocumentCategory,
    subcategory: doc.subcategory,
    date: /^\d{4}-\d{2}-\d{2}$/.test(doc.date) ? doc.date : "",
    issuer: doc.issuer,
    url: doc.source_url,
  };
}

export function EditDocumentDialog({ doc, onClose }: { doc: DocumentSummary | null; onClose: () => void }) {
  return (
    <Dialog open={!!doc} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Edit metadata</DialogTitle>
          <DialogDescription>Saving re-indexes the document so citations show the new details.</DialogDescription>
        </DialogHeader>
        {doc && <EditForm key={doc.doc_id} doc={doc} onClose={onClose} />}
      </DialogContent>
    </Dialog>
  );
}

function EditForm({ doc, onClose }: { doc: DocumentSummary; onClose: () => void }) {
  const update = useUpdateDocument();
  const initial = toMetadata(doc);
  const [form, setForm] = useState(initial);
  const changes = Object.fromEntries(
    Object.entries(form).filter(([k, v]) => v !== initial[k as keyof DocumentMetadata] && !(k === "date" && !v)),
  ) as Partial<DocumentMetadata>;
  const dirty = Object.keys(changes).length > 0;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    update.mutate(
      { docId: doc.doc_id, patch: changes },
      {
        onSuccess: ({ job }) => {
          toast.success("Metadata saved", { description: job ? "Re-indexing has started." : "The PDF is missing, so it wasn’t re-indexed." });
          onClose();
        },
        onError: (err) => toast.error(errorMessage(err)),
      },
    );
  };

  return (
    <form onSubmit={submit} className="space-y-4">
      <p className="truncate rounded-lg bg-muted/50 px-3 py-2 font-mono text-xs text-muted-foreground" title={doc.filename}>
        {doc.filename}
      </p>
      <MetadataFields value={form} onChange={setForm} />
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" disabled={!dirty || form.name.trim().length < 3 || update.isPending}>
          {update.isPending && <Loader2Icon className="animate-spin" />}
          Save and re-index
        </Button>
      </DialogFooter>
    </form>
  );
}

export function DeleteDocumentDialog({ doc, onClose }: { doc: DocumentSummary | null; onClose: () => void }) {
  const del = useDeleteDocument();
  const [deleteFile, setDeleteFile] = useState(false);
  // Keeps the text in place while the dialog animates out.
  const [shown, setShown] = useState(doc);
  if (doc && doc !== shown) setShown(doc);
  return (
    <AlertDialog
      open={!!doc}
      onOpenChange={(o) => {
        if (!o) {
          setDeleteFile(false);
          onClose();
        }
      }}
    >
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Remove this document?</AlertDialogTitle>
          <AlertDialogDescription>
            “{shown?.name}” and its {shown?.chunks.toLocaleString()} passages will no longer be used for answers. Past answers keep
            their citations.
          </AlertDialogDescription>
        </AlertDialogHeader>
        {shown?.has_file && (
          <label className="flex items-center gap-2.5 text-sm">
            <Checkbox checked={deleteFile} onCheckedChange={(v) => setDeleteFile(v === true)} />
            Also delete the PDF from the server
          </label>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            variant="destructive"
            onClick={() =>
              doc &&
              del.mutate(
                { docId: doc.doc_id, deleteFile },
                {
                  onSuccess: () => toast.success(`Removed ${doc.name}`),
                  onError: (err) => toast.error(errorMessage(err)),
                },
              )
            }
          >
            Remove
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
