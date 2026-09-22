"use client";

import { useCallback, useEffect, useState } from "react";
import { CloudUpload, FileUp } from "lucide-react";
import { api } from "@/lib/api";
import { Badge, Button, EmptyState, Input, Spinner, useToast } from "@/components/ui";
import { cn } from "@/lib/utils";

const ACCESS = ["public", "internal", "restricted"];

export function UploadPanel({ token, onDone }: { token: string; onDone: () => void }) {
  const { push } = useToast();
  const [drag, setDrag] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [meta, setMeta] = useState({ department: "", location: "", policy_category: "", access_level: "public" });
  const [pct, setPct] = useState<number | null>(null);

  const submit = useCallback(async () => {
    if (!file) return;
    setPct(0);
    try {
      const res = await api.upload(token, file, {
        department: meta.department || undefined,
        location: meta.location || undefined,
        policy_category: meta.policy_category || undefined,
        access_level: meta.access_level,
      }, setPct);
      push("ok", `${file.name} queued (v${res.version})`);
      setFile(null);
      onDone();
    } catch {
      push("err", "Upload failed — check file type and permissions.");
    } finally {
      setPct(null);
    }
  }, [file, meta, token, onDone, push]);

  return (
    <div className="rounded-2xl border border-white/40 bg-white/70 p-5 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70">
      <h3 className="font-display text-sm font-bold">Upload policy document</h3>
      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); setFile(e.dataTransfer.files?.[0] ?? null); }}
        className={cn(
          "mt-3 flex cursor-pointer flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors",
          drag ? "border-brand-500 bg-brand-500/5" : "border-slate-300 dark:border-slate-700",
        )}
        onClick={() => document.getElementById("hr-file")?.click()}
        role="button"
        aria-label="Choose a policy file"
      >
        <CloudUpload size={26} className="text-brand-500" />
        <p className="text-sm font-semibold">{file ? file.name : "Drop a file or click to browse"}</p>
        <p className="text-xs text-slate-500">PDF · DOCX · XLSX · TXT · MD · HTML</p>
        <input
          id="hr-file"
          type="file"
          className="hidden"
          accept=".pdf,.docx,.xlsx,.txt,.md,.html,.htm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <Input label="Department" value={meta.department} onChange={(e) => setMeta({ ...meta, department: e.target.value })} placeholder="HR" />
        <Input label="Location" value={meta.location} onChange={(e) => setMeta({ ...meta, location: e.target.value })} placeholder="India" />
        <Input label="Category" value={meta.policy_category} onChange={(e) => setMeta({ ...meta, policy_category: e.target.value })} placeholder="Leave" />
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">Access level</span>
          <select
            value={meta.access_level}
            onChange={(e) => setMeta({ ...meta, access_level: e.target.value })}
            className="w-full rounded-xl border border-slate-300 bg-white/80 px-3.5 py-2.5 text-sm dark:border-slate-700 dark:bg-slate-900/80"
          >
            {ACCESS.map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </label>
      </div>
      {pct !== null && (
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
          <div className="h-full bg-gradient-to-r from-brand-500 to-accent-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      )}
      <Button onClick={submit} disabled={!file || pct !== null} className="mt-4 w-full">
        {pct !== null ? (<><Spinner /> Uploading…</>) : (<><FileUp size={15} /> Ingest document</>)}
      </Button>
    </div>
  );
}

export function DocLibrary({ token, refreshKey }: { token: string; refreshKey: number }) {
  const [docs, setDocs] = useState<Awaited<ReturnType<typeof api.documents>>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.documents(token).then(setDocs).catch(() => setDocs([])).finally(() => setLoading(false));
  }, [token, refreshKey]);

  if (loading) return <p className="flex items-center gap-2 p-6 text-sm text-slate-500"><Spinner /> Loading library…</p>;
  if (!docs.length) return <EmptyState icon={<FileUp size={22} />} title="No documents yet" hint="Upload your first HR policy to build the knowledge base." />;

  const tone = (s: string): "green" | "red" | "amber" => (s === "ready" ? "green" : s === "failed" ? "red" : "amber");
  return (
    <ul className="divide-y divide-slate-200/70 dark:divide-slate-800">
      {docs.map((d) => (
        <li key={d.id} className="flex items-center gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{d.file_name}</p>
            <p className="text-xs text-slate-500">v{d.version}{d.policy_category ? ` · ${d.policy_category}` : ""}</p>
          </div>
          <Badge tone={tone(d.status)}>{d.status}</Badge>
        </li>
      ))}
    </ul>
  );
}
