"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Info, XCircle } from "lucide-react";
import { cn, uid } from "@/lib/utils";

/* ---------- Button ---------- */
export function Button({
  children,
  variant = "primary",
  className,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "ghost" | "outline" | "danger" }) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none",
        variant === "primary" &&
          "bg-gradient-to-r from-brand-600 to-accent-600 text-white shadow-glow hover:brightness-110",
        variant === "ghost" && "text-slate-600 hover:bg-slate-200/60 dark:text-slate-300 dark:hover:bg-slate-800",
        variant === "outline" &&
          "border border-slate-300 text-slate-700 hover:border-brand-400 hover:text-brand-600 dark:border-slate-700 dark:text-slate-200",
        variant === "danger" && "bg-red-600 text-white hover:bg-red-500",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

/* ---------- Card ---------- */
export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/40 bg-white/70 shadow-card backdrop-blur-xl",
        "dark:border-slate-800 dark:bg-slate-900/70",
        className,
      )}
    >
      {children}
    </div>
  );
}

/* ---------- Input ---------- */
export function Input(props: React.InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  const { label, className, ...rest } = props;
  return (
    <label className="block">
      {label && (
        <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
          {label}
        </span>
      )}
      <input
        className={cn(
          "w-full rounded-xl border border-slate-300 bg-white/80 px-3.5 py-2.5 text-sm text-slate-900 placeholder:text-slate-400",
          "dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-100",
          className,
        )}
        {...rest}
      />
    </label>
  );
}

/* ---------- Badge ---------- */
export function Badge({ children, tone = "slate" }: { children: React.ReactNode; tone?: "slate" | "brand" | "green" | "amber" | "red" }) {
  const tones: Record<string, string> = {
    slate: "bg-slate-200/70 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
    brand: "bg-brand-100 text-brand-700 dark:bg-brand-900/50 dark:text-brand-300",
    green: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300",
    amber: "bg-amber-100 text-amber-700 dark:bg-amber-900/50 dark:text-amber-300",
    red: "bg-red-100 text-red-700 dark:bg-red-900/50 dark:text-red-300",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold", tones[tone])}>
      {children}
    </span>
  );
}

/* ---------- Spinner ---------- */
export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-label="loading"
      className={cn("inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent", className)}
    />
  );
}

/* ---------- EmptyState ---------- */
export function EmptyState({ icon, title, hint }: { icon: React.ReactNode; title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <div className="mb-1 flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-500/20 to-accent-500/20 text-brand-600 dark:text-brand-300">
        {icon}
      </div>
      <p className="font-display text-base font-semibold">{title}</p>
      {hint && <p className="max-w-xs text-sm text-slate-500 dark:text-slate-400">{hint}</p>}
    </div>
  );
}

/* ---------- Stat ---------- */
export function Stat({ label, value, sub, icon }: { label: string; value: string; sub?: string; icon?: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">{label}</p>
        {icon}
      </div>
      <p className="mt-1 font-display text-2xl font-bold">{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{sub}</p>}
    </Card>
  );
}

/* ---------- Toast ---------- */
type Toast = { id: string; kind: "ok" | "err" | "info"; text: string };
const ToastCtx = createContext<{ push: (kind: Toast["kind"], text: string) => void } | null>(null);

export function Toaster({ children }: { children?: React.ReactNode }) {
  const [items, setItems] = useState<Toast[]>([]);
  const push = useCallback((kind: Toast["kind"], text: string) => {
    const id = uid();
    setItems((xs) => [...xs, { id, kind, text }]);
    setTimeout(() => setItems((xs) => xs.filter((t) => t.id !== id)), 4200);
  }, []);
  const value = useMemo(() => ({ push }), [push]);
  const icons = { ok: <CheckCircle2 size={16} />, err: <XCircle size={16} />, info: <Info size={16} /> };
  return (
    <ToastCtx.Provider value={value}>
      {children}
      <div aria-live="polite" className="pointer-events-none fixed bottom-5 right-5 z-50 flex w-80 flex-col gap-2">
        <AnimatePresence>
          {items.map((t) => (
            <motion.div
              key={t.id}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 8 }}
              className="pointer-events-auto flex items-center gap-2 rounded-xl border border-slate-200 bg-white/95 px-3.5 py-2.5 text-sm shadow-card backdrop-blur dark:border-slate-700 dark:bg-slate-900/95"
            >
              <span className={t.kind === "ok" ? "text-emerald-500" : t.kind === "err" ? "text-red-500" : "text-brand-500"}>
                {icons[t.kind]}
              </span>
              {t.text}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </ToastCtx.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useToast() {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast outside Toaster — is <Toaster/> mounted in layout?");
  return ctx;
}
