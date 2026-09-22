"use client";

import { useState } from "react";
import { FileStack, ShieldCheck, Activity } from "lucide-react";
import { TopBar } from "@/components/chrome";
import { Card } from "@/components/ui";
import { DocLibrary, UploadPanel } from "@/components/admin/UploadPanel";
import { UserManager } from "@/components/admin/UserManager";
import { Insights } from "@/components/admin/Insights";
import { useRequireAuth } from "@/lib/auth";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "docs", label: "Documents", icon: FileStack },
  { id: "users", label: "Users", icon: ShieldCheck },
  { id: "insights", label: "Insights", icon: Activity },
] as const;

export default function AdminPage() {
  const auth = useRequireAuth();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("docs");
  const [refreshKey, setRefreshKey] = useState(0);

  if (!auth) {
    return <main className="flex min-h-screen items-center justify-center text-sm text-slate-500">Loading…</main>;
  }
  const privileged = auth.user.role !== "employee";
  if (!privileged) {
    return (
      <div className="flex min-h-screen flex-col">
        <TopBar title="Admin console" />
        <main className="mx-auto w-full max-w-6xl px-4 py-10 text-center text-sm text-slate-500">
          Admin console is restricted to HR staff. Your role: <strong>{auth.user.role}</strong>.
        </main>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <TopBar title="Admin console" subtitle="Documents · people · live insights" />
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-4">
        <div className="mb-4 flex gap-1.5 rounded-2xl border border-white/40 bg-white/60 p-1 backdrop-blur-xl dark:border-slate-800 dark:bg-slate-900/60" role="tablist" aria-label="Admin sections">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => setTab(t.id)}
              className={cn(
                "flex flex-1 items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all",
                tab === t.id
                  ? "bg-gradient-to-r from-brand-600 to-accent-600 text-white shadow-glow"
                  : "text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100",
              )}
            >
              <t.icon size={15} /> <span className="hidden sm:inline">{t.label}</span>
            </button>
          ))}
        </div>

        {tab === "docs" && (
          <div className="grid gap-4 lg:grid-cols-5">
            <div className="lg:col-span-2">
              <UploadPanel token={auth.token} onDone={() => setRefreshKey((k) => k + 1)} />
            </div>
            <Card className="lg:col-span-3">
              <h3 className="border-b border-slate-200/70 px-4 py-3 font-display text-sm font-bold dark:border-slate-800">Document library</h3>
              <DocLibrary token={auth.token} refreshKey={refreshKey} />
            </Card>
          </div>
        )}
        {tab === "users" && (
          <Card>
            <h3 className="border-b border-slate-200/70 px-4 py-3 font-display text-sm font-bold dark:border-slate-800">People & roles</h3>
            <UserManager token={auth.token} />
          </Card>
        )}
        {tab === "insights" && (
          <Card>
            <h3 className="border-b border-slate-200/70 px-4 py-3 font-display text-sm font-bold dark:border-slate-800">Live insights & monitoring</h3>
            <Insights token={auth.token} refreshKey={refreshKey} />
          </Card>
        )}
      </main>
    </div>
  );
}
