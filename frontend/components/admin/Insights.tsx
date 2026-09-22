"use client";

import { useEffect, useState } from "react";
import { Activity, Clock3, ThumbsUp, Zap, Coins, MessageSquareQuote } from "lucide-react";
import { Overview, api } from "@/lib/api";
import { EmptyState, Spinner, Stat } from "@/components/ui";

export function Insights({ token, refreshKey }: { token: string; refreshKey: number }) {
  const [data, setData] = useState<Overview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api.overview(token).then(setData).catch(() => setData(null)).finally(() => setLoading(false));
  }, [token, refreshKey]);

  if (loading) return <p className="flex items-center gap-2 p-6 text-sm text-slate-500"><Spinner /> Loading insights…</p>;
  if (!data) return <EmptyState icon={<Activity size={22} />} title="No telemetry yet" hint="Ask questions in chat, then return for live stats." />;

  const satisfaction = data.feedback.satisfaction == null ? "—" : `${Math.round(data.feedback.satisfaction * 100)}%`;
  return (
    <div className="space-y-4 p-4">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Queries" value={String(data.query_volume)} icon={<MessageSquareQuote size={15} className="text-brand-500" />} />
        <Stat label="Avg latency" value={`${(data.avg_latency_ms / 1000).toFixed(1)}s`} icon={<Clock3 size={15} className="text-amber-500" />} />
        <Stat label="Cache hits" value={`${Math.round(data.cache_hit_rate * 100)}%`} sub="target > 60%" icon={<Zap size={15} className="text-emerald-500" />} />
        <Stat label="Satisfaction" value={satisfaction} sub={`👍 ${data.feedback.up} · 👎 ${data.feedback.down}`} icon={<ThumbsUp size={15} className="text-accent-500" />} />
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="rounded-2xl border border-slate-200/70 p-4 dark:border-slate-800">
          <h4 className="flex items-center gap-1.5 text-sm font-bold"><MessageSquareQuote size={14} /> Top questions</h4>
          <ol className="mt-2 space-y-1.5 text-sm">
            {data.top_questions.length === 0 && <li className="text-xs text-slate-500">No data yet.</li>}
            {data.top_questions.map((t, i) => (
              <li key={t.query} className="flex items-center gap-2">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-brand-600/10 text-[11px] font-bold text-brand-600 dark:text-brand-300">{i + 1}</span>
                <span className="min-w-0 flex-1 truncate">{t.query}</span>
                <span className="text-xs text-slate-400">×{t.count}</span>
              </li>
            ))}
          </ol>
        </div>
        <div className="rounded-2xl border border-slate-200/70 p-4 dark:border-slate-800">
          <h4 className="flex items-center gap-1.5 text-sm font-bold"><Coins size={14} /> Token usage</h4>
          <p className="mt-2 font-display text-2xl font-bold">{(data.tokens.in + data.tokens.out).toLocaleString()}</p>
          <p className="text-xs text-slate-500">in {data.tokens.in.toLocaleString()} · out {data.tokens.out.toLocaleString()} · Groq free tier ≈ $0</p>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="img" aria-label={`Cache hit rate ${Math.round(data.cache_hit_rate * 100)} percent`}>
            <div className="h-full bg-gradient-to-r from-emerald-500 to-brand-500" style={{ width: `${Math.round(data.cache_hit_rate * 100)}%` }} />
          </div>
          <p className="mt-1 text-xs text-slate-500">Cache hit-rate gauge</p>
        </div>
      </div>
    </div>
  );
}
