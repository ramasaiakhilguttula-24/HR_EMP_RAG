"use client";

import { useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { UserPlus } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";
import { Button, Input, useToast } from "@/components/ui";
import { ThemeToggle } from "@/components/chrome";

export default function RegisterPage() {
  const { register } = useAuth();
  const { push } = useToast();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      await register(fullName.trim(), email.trim(), password);
      push("ok", "Account created — welcome!");
    } catch (err) {
      push("err", err instanceof ApiError ? `Sign up failed (${err.status})` : "Sign up failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="relative flex min-h-screen items-center justify-center p-6">
      <div className="absolute left-6 top-6"><ThemeToggle /></div>
      <motion.form
        onSubmit={submit}
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-sm rounded-3xl border border-white/40 bg-white/70 p-8 shadow-card backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/70"
      >
        <h2 className="font-display text-2xl font-bold">Create account</h2>
        <p className="mb-6 mt-1 text-sm text-slate-500 dark:text-slate-400">Join with your work email.</p>
        <div className="space-y-4">
          <Input label="Full name" required value={fullName} onChange={(e) => setFullName(e.target.value)} placeholder="Aarav Sharma" autoComplete="name" />
          <Input label="Work email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" autoComplete="email" />
          <Input label="Password" type="password" required minLength={8} value={password} onChange={(e) => setPassword(e.target.value)} placeholder="8+ chars, upper, lower, digit" autoComplete="new-password" />
        </div>
        <Button type="submit" disabled={busy} className="mt-6 w-full">
          {busy ? "Creating…" : (<><UserPlus size={16} /> Sign up</>)}
        </Button>
        <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
          Have an account? <Link href="/login" className="font-semibold text-brand-600 hover:underline dark:text-brand-300">Sign in</Link>
        </p>
      </motion.form>
    </main>
  );
}
