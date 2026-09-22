"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Bot, ChevronDown, User, Zap } from "lucide-react";
import { useState } from "react";
import type { ChatMessage } from "@/lib/api";
import { timeAgo } from "@/lib/utils";
import { cn } from "@/lib/utils";
import { CitationCard, FeedbackButtons } from "@/components/citations/CitationCard";

function renderText(text: string): React.ReactNode[] {
  // lightweight **bold** + [n] citation highlight
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\])/g);
  return parts.map((p, i) => {
    if (/^\*\*[^*]+\*\*$/.test(p)) return <strong key={i}>{p.slice(2, -2)}</strong>;
    if (/^\[\d+\]$/.test(p))
      return (
        <span key={i} className="font-semibold text-brand-600 dark:text-brand-300">
          {p}
        </span>
      );
    return <span key={i}>{p}</span>;
  });
}

export function ChatWindow({
  messages,
  streaming,
  onVote,
}: {
  messages: ChatMessage[];
  streaming: boolean;
  onVote: (id: string, v: 1 | -1) => void;
}) {
  return (
    <div aria-live="polite" className="flex flex-col gap-4">
      <AnimatePresence initial={false}>
        {messages.map((m) => (
          <motion.div
            key={m.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn("flex gap-3", m.role === "user" ? "flex-row-reverse" : "")}
          >
            <span
              className={cn(
                "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl",
                m.role === "user"
                  ? "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900"
                  : "bg-gradient-to-br from-brand-500 to-accent-500 text-white shadow-glow",
              )}
            >
              {m.role === "user" ? <User size={15} /> : <Bot size={15} />}
            </span>
            <div className={cn("max-w-[85%] sm:max-w-[75%]", m.role === "user" ? "text-right" : "")}>
              <div
                className={cn(
                  "inline-block rounded-2xl px-4 py-3 text-left text-sm shadow-card",
                  m.role === "user"
                    ? "rounded-br-md bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900"
                    : "rounded-bl-md border border-white/40 bg-white/80 backdrop-blur-xl dark:border-slate-700/60 dark:bg-slate-900/70",
                )}
              >
                <div className={cn("prose-chat", m.role === "assistant" && streaming && "stream-caret")}>
                  {m.text ? renderText(m.text) : <span className="text-slate-400">Thinking…</span>}
                </div>
                {m.role === "assistant" && m.citations.length > 0 && <CitationCard citations={m.citations} />}
                {m.role === "assistant" && m.steps && m.steps.length > 0 && <StepTrace steps={m.steps} />}
              </div>
              <div className="mt-1 flex items-center gap-2 px-1 text-[11px] text-slate-400">
                <span>{timeAgo(m.createdAt)}</span>
                {m.cached && <span className="inline-flex items-center gap-0.5 font-semibold text-emerald-500"><Zap size={10} /> cached</span>}
                {m.latencyMs != null && m.role === "assistant" && <span>{(m.latencyMs / 1000).toFixed(1)}s</span>}
                {m.role === "assistant" && m.text && (
                  <FeedbackButtons value={m.feedback} onVote={(v) => onVote(m.id, v)} />
                )}
              </div>
            </div>
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
}

function StepTrace({ steps }: { steps: NonNullable<ChatMessage["steps"]> }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-slate-200/70 bg-slate-50/70 dark:border-slate-700/60 dark:bg-slate-950/40">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300"
      >
        Agent trace · {steps.length} step{steps.length > 1 ? "s" : ""}
        <ChevronDown size={13} className={cn("ml-auto transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="space-y-1.5 px-3 pb-3 text-xs">
          {steps.map((s, i) => (
            <li key={i} className="rounded-lg bg-white/70 p-2 dark:bg-slate-900/60">
              <p className="font-mono font-semibold text-brand-600 dark:text-brand-300">{i + 1}. {s.tool}</p>
              <p className="mt-0.5 break-words text-slate-500 dark:text-slate-400">
                {JSON.stringify(s.observation).slice(0, 220)}
              </p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
