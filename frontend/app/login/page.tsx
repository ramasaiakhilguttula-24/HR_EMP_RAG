"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { LogIn, Sparkles } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Input, useToast } from "@/components/ui";
import { ThemeToggle } from "@/components/chrome";

export default function LoginPage() {
  const { login } = useAuth();
  const { push } = useToast();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await login(email.trim(), password);
      push("ok", "Welcome back!");
    } catch (err) {
      push("err", err instanceof ApiError ? `Login failed (${err.status})` : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="grid min-h-screen lg:grid-cols-2">
      <section className="relative hidden flex-col justify-between overflow-hidden bg-slate-950 p-10 text-white lg:flex">
        <div className="absolute inset-0 bg-gradient-to-br from-brand-700 via-slate-950 to-accent-600/40" />
        <div className="absolute -left-20 top-1/3 h-72 w-72 animate-float rounded-full bg-brand-500/30 blur-3xl" />
        <div className="absolute bottom-10 right-10 h-64 w-64 animate-float rounded-full bg-accent-500/20 blur-3xl" style={{ animationDelay: "-3s" }} />
        <div className="relative flex items-center gap-2.5">
          <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-400 to-accent-500 font-display text-lg font-bold shadow-glow">P</span>
          <span className="font-display text-xl font-bold">Prism HR</span>
        </div>
        <div className="relative">
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            className="font-display text-4xl font-bold leading-tight"
          >
            Every HR answer,
            <br />
            <span className="bg-gradient-to-r from-brand-300 to-accent-300 bg-clip-text text-transparent">cited and certain.</span>
          </motion.h1>
          <ul className="mt-6 space-y-2.5 text-sm text-slate-300">
            {["Streaming answers with source citations", "Role-aware policies for every employee", "HR admin console with live insights"].map((t) => (
              <li key={t} className="flex items-center gap-2">
                <Sparkles size={14} className="text-accent-300" /> {t}
              </li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-slate-500">SOC-2 minded · PII-masked · RBAC enforced</p>
      </section>

      <section className="relative flex items-center justify-center p-6">
        <div className="absolute right-6 top-6"><ThemeToggle /></div>
        <motion.form
          onSubmit={submit}
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-sm rounded-3xl border border-white/40 bg-white/70 p-8 shadow-card backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70"
        >
          <h2 className="font-display text-2xl font-bold">Sign in</h2>
          <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">Ask HR anything, in plain language.</p>
          <div className="space-y-4">
            <Input label="Work email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
            <Input label="Password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" autoComplete="current-password" />
          </div>
          <Button type="submit" disabled={busy} className="mt-6 w-full">
            {busy ? "Signing in…" : (<><LogIn size={16} /> Sign in</>)}
          </Button>
          <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
            New here? <Link href="/register" className="font-semibold text-brand-600 hover:underline dark:text-brand-300">Create an account</Link>
          </p>
        </motion.form>
      </section>
    </main>
  );
}
