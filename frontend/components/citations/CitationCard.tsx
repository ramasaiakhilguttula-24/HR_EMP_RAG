"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BookOpenText, ChevronDown, FileText, ThumbsDown, ThumbsUp } from "lucide-react";
import type { Citation } from "@/lib/api";
import { cn } from "@/lib/utils";

export function CitationCard({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);
  if (!citations.length) return null;
  return (
    <div className="mt-2.5 overflow-hidden rounded-xl border border-brand-200/60 bg-brand-50/60 dark:border-brand-800/40 dark:bg-brand-950/30">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-semibold text-brand-700 dark:text-brand-300"
      >
        <BookOpenText size={14} />
        {citations.length} source{citations.length > 1 ? "s" : ""}
        <ChevronDown size={14} className={cn("ml-auto transition-transform", open && "rotate-180")} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <ul className="space-y-1.5 px-3 pb-3">
              {citations.map((c) => (
                <li
                  key={c.index}
                  className="rounded-lg border border-slate-200/70 bg-white/80 p-2.5 text-xs dark:border-slate-700/60 dark:bg-slate-900/60"
                >
                  <p className="flex items-center gap-1.5 font-semibold text-slate-700 dark:text-slate-200">
                    <FileText size={12} className="shrink-0 text-brand-500" />
                    [{c.index}] {c.document}
                    {c.page != null && <span className="font-normal text-slate-500">· p{c.page}</span>}
                  </p>
                  {c.section && <p className="mt-0.5 text-slate-500 dark:text-slate-400">{c.section}</p>}
                  <p className="mt-1 line-clamp-3 text-slate-600 dark:text-slate-300">“{c.excerpt}”</p>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function FeedbackButtons({
  value,
  onVote,
}: {
  value?: 1 | -1;
  onVote: (v: 1 | -1) => void;
}) {
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Rate this answer">
      {([1, -1] as const).map((v) => (
        <button
          key={v}
          onClick={() => onVote(v)}
          aria-label={v === 1 ? "Helpful" : "Not helpful"}
          aria-pressed={value === v}
          className={cn(
            "flex h-7 w-7 items-center justify-center rounded-lg transition-colors",
            value === v
              ? v === 1
                ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                : "bg-red-500/15 text-red-600 dark:text-red-400"
              : "text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 dark:hover:bg-slate-800 dark:hover:text-slate-300",
          )}
        >
          {v === 1 ? <ThumbsUp size={13} /> : <ThumbsDown size={13} />}
        </button>
      ))}
    </div>
  );
}
