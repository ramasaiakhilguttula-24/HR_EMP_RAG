"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Bot, MessageSquarePlus, PanelLeft, Sparkles, Trash2 } from "lucide-react";
import { TopBar } from "@/components/chrome";
import { ChatWindow } from "@/components/chat/ChatWindow";
import { Composer } from "@/components/chat/Composer";
import { Badge, Button, EmptyState, useToast } from "@/components/ui";
import { ApiError, ChatMessage, api } from "@/lib/api";
import { useRequireAuth } from "@/lib/auth";
import { cn, timeAgo, uid } from "@/lib/utils";

interface Session {
  id: string;
  title: string;
  updatedAt: string;
  messages: ChatMessage[];
}

const SUGGESTIONS = [
  "How many days of annual leave do I get?",
  "What is my notice period with 3 years of tenure?",
  "How many days can I work from home?",
  "What does Article 12.3 of the POSH policy say?",
];

export default function ChatPage() {
  const auth = useRequireAuth();
  const { push } = useToast();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [agentMode, setAgentMode] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("hr-sessions");
      if (raw) {
        const parsed = JSON.parse(raw) as Session[];
        setSessions(parsed);
        setActiveId(parsed[0]?.id ?? null);
      }
    } catch {
      /* start fresh */
    }
  }, []);

  useEffect(() => {
    localStorage.setItem("hr-sessions", JSON.stringify(sessions.slice(0, 20)));
  }, [sessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  });

  const active = useMemo(() => sessions.find((s) => s.id === activeId) ?? null, [sessions, activeId]);

  const patchMessages = useCallback(
    (sid: string, fn: (msgs: ChatMessage[]) => ChatMessage[]) => {
      setSessions((xs) =>
        xs.map((s) => (s.id === sid ? { ...s, messages: fn(s.messages), updatedAt: new Date().toISOString() } : s)),
      );
    },
    [],
  );

  const newChat = useCallback(() => {
    const s: Session = { id: uid(), title: "New conversation", updatedAt: new Date().toISOString(), messages: [] };
    setSessions((xs) => [s, ...xs]);
    setActiveId(s.id);
  }, []);

  useEffect(() => {
    if (!activeId && sessions.length === 0) newChat();
  }, [activeId, sessions.length, newChat]);

  const send = useCallback(
    async (text: string) => {
      if (!auth || busy) return;
      let sid = activeId;
      if (!sid) {
        sid = uid();
        setSessions((xs) => [{ id: sid as string, title: text.slice(0, 42), updatedAt: new Date().toISOString(), messages: [] }, ...xs]);
        setActiveId(sid);
      } else {
        setSessions((xs) => xs.map((s) => (s.id === sid ? { ...s, title: s.messages.length === 0 ? text.slice(0, 42) : s.title } : s)));
      }
      const target = sid as string;
      const userMsg: ChatMessage = { id: uid(), role: "user", text, citations: [], createdAt: new Date().toISOString() };
      const botMsg: ChatMessage = { id: uid(), role: "assistant", text: "", citations: [], createdAt: new Date().toISOString() };
      patchMessages(target, (xs) => [...xs, userMsg, botMsg]);
      setBusy(true);
      const abort = new AbortController();
      abortRef.current = abort;
      try {
        if (agentMode) {
          const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/v1/agent/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${auth.token}` },
            body: JSON.stringify({ query: text }),
            signal: abort.signal,
          });
          if (!res.ok) throw new ApiError(res.status, await res.text());
          const data = await res.json();
          patchMessages(target, (xs) =>
            xs.map((m) =>
              m.id === botMsg.id
                ? { ...m, text: data.answer, citations: data.citations ?? [], steps: data.steps, escalated: data.escalated, latencyMs: data.latency_ms }
                : m,
            ),
          );
        } else {
          await api.streamChat(auth.token, "/api/v1/chat/stream", { query: text }, (ev) => {
            if (ev.type === "citations") {
              patchMessages(target, (xs) => xs.map((m) => (m.id === botMsg.id ? { ...m, citations: ev.citations } : m)));
            } else if (ev.type === "token") {
              patchMessages(target, (xs) => xs.map((m) => (m.id === botMsg.id ? { ...m, text: m.text + ev.token } : m)));
            } else if (ev.type === "answer") {
              patchMessages(target, (xs) =>
                xs.map((m) => (m.id === botMsg.id ? { ...m, text: ev.answer, fallback: ev.fallback } : m)),
              );
            }
          }, abort.signal);
        }
      } catch (err) {
        if ((err as Error).name === "AbortError") {
          patchMessages(target, (xs) => xs.map((m) => (m.id === botMsg.id && !m.text ? { ...m, text: "_Stopped._" } : m)));
        } else {
          const msg = err instanceof ApiError && err.status === 403 ? "Blocked by policy guard." : "Something went wrong. Try again.";
          push("err", msg);
          patchMessages(target, (xs) => xs.filter((m) => m.id !== botMsg.id));
        }
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [auth, busy, activeId, patchMessages, push, agentMode],
  );

  const vote = useCallback(
    async (id: string, v: 1 | -1) => {
      if (!auth || !active) return;
      patchMessages(active.id, (xs) => xs.map((m) => (m.id === id ? { ...m, feedback: v } : m)));
      push("ok", v === 1 ? "Thanks for the feedback!" : "Noted — we'll do better.");
    },
    [auth, active, patchMessages, push],
  );

  if (!auth) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading…</main>;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar title="Policy Assistant" subtitle={agentMode ? "Agentic mode · multi-step reasoning" : "Ask HR anything"} />
      <div className="mx-auto flex w-full max-w-6xl flex-1 gap-4 px-4 py-4">
        {/* sidebar */}
        <AnimatePresence initial={false}>
          {sidebarOpen && (
            <motion.aside
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 248, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              className="hidden shrink-0 overflow-hidden md:block"
            >
              <div className="flex h-full w-[248px] flex-col rounded-2xl border border-white/40 bg-white/60 p-3 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/60">
                <Button onClick={newChat} className="w-full !py-2 text-[13px]">
                  <MessageSquarePlus size={15} /> New chat
                </Button>
                <div className="mt-3 flex-1 space-y-1 overflow-y-auto">
                  {sessions.map((s) => (
                    <div key={s.id} className="group flex items-center gap-1">
                      <button
                        onClick={() => setActiveId(s.id)}
                        className={cn(
                          "min-w-0 flex-1 rounded-xl px-3 py-2 text-left text-[13px] transition-colors",
                          s.id === activeId
                            ? "bg-brand-600/10 font-semibold text-brand-700 dark:text-brand-200"
                            : "text-slate-600 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800",
                        )}
                      >
                        <span className="block truncate">{s.title}</span>
                        <span className="text-[11px] text-slate-400">{timeAgo(s.updatedAt)}</span>
                      </button>
                      <button
                        aria-label="Delete conversation"
                        onClick={() => {
                          setSessions((xs) => xs.filter((x) => x.id !== s.id));
                          if (activeId === s.id) setActiveId(null);
                        }}
                        className="hidden h-7 w-7 items-center justify-center rounded-lg text-slate-400 hover:bg-red-500/10 hover:text-red-500 group-hover:flex"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </motion.aside>
          )}
        </AnimatePresence>

        {/* main column */}
        <section className="flex min-w-0 flex-1 flex-col rounded-2xl border border-white/40 bg-white/50 p-4 backdrop-blur-xl sm:p-5 dark:border-slate-800 dark:bg-slate-900/50">
          <div className="mb-3 flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen((o) => !o)}
              aria-label="Toggle history"
              className="hidden h-8 w-8 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-200/60 md:flex dark:text-slate-400"
            >
              <PanelLeft size={16} />
            </button>
            <div className="flex rounded-xl bg-slate-200/60 p-0.5 text-xs font-semibold dark:bg-slate-800" role="tablist" aria-label="Assistant mode">
              {(["assist", "agent"] as const).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={(m === "agent") === agentMode}
                  onClick={() => setAgentMode(m === "agent")}
                  className={cn(
                    "flex items-center gap-1.5 rounded-[10px] px-3 py-1.5 transition-all",
                    (m === "agent") === agentMode
                      ? "bg-white text-brand-700 shadow dark:bg-slate-950 dark:text-brand-200"
                      : "text-slate-500 dark:text-slate-400",
                  )}
                >
                  {m === "agent" && <Bot size={13} />}
                  {m === "assist" ? "Assistant" : "Agent"}
                </button>
              ))}
            </div>
            {agentMode && <Badge tone="brand">ReAct · max 5 steps</Badge>}
          </div>

          <div className="min-h-[40vh] flex-1">
            {!active || active.messages.length === 0 ? (
              <EmptyState
                icon={<Sparkles size={22} />}
                title={agentMode ? "Ask a complex, multi-step question" : "What do you want to know?"}
                hint={agentMode ? "Try: I have 3.5 years of tenure. How much notice must I serve?" : undefined}
              />
            ) : (
              <ChatWindow messages={active.messages} streaming={busy} onVote={vote} />
            )}
            <div ref={bottomRef} />
          </div>

          {!active || active.messages.length > 0 ? null : (
            <div className="mb-3 grid gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  disabled={busy}
                  className="rounded-xl border border-slate-300/60 bg-white/60 px-3 py-2 text-left text-[13px] text-slate-600 transition-all hover:border-brand-400 hover:text-brand-700 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300"
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          <div className="sticky bottom-0 pt-2">
            <Composer busy={busy} onSend={send} onStop={() => abortRef.current?.abort()} />
            <p className="mt-1.5 text-center text-[11px] text-slate-400">
              Grounded in HR policy docs · PII masked · {agentMode ? "agentic reasoning" : "cited answers"}
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
