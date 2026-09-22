"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutDashboard, MessageSquareText, Moon, Sparkles, Sun, LogOut } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label="Toggle theme"
      className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-300/60 bg-white/60 text-slate-600 backdrop-blur hover:text-brand-600 dark:border-slate-700 dark:bg-slate-900/60 dark:text-slate-300"
    >
      {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
    </button>
  );
}

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link href="/chat" className="flex items-center gap-2.5">
      <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-accent-500 font-display text-base font-bold text-white shadow-glow">P</span>
      {!compact && <span className="font-display text-lg font-bold">Prism HR</span>}
    </Link>
  );
}

export function TopBar({ title, subtitle }: { title: string; subtitle?: string }) {
  const { user, logout } = useAuth();
  const pathname = usePathname();
  const isPrivileged = user && user.role !== "employee";
  return (
    <header className="sticky top-0 z-20 border-b border-slate-200/60 bg-white/70 backdrop-blur-xl dark:border-slate-800/60 dark:bg-slate-950/70">
      <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
        <Brand compact />
        <div className="ml-2 hidden sm:block">
          <h1 className="font-display text-sm font-bold leading-none">{title}</h1>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{subtitle}</p>}
        </div>
        <nav className="ml-auto flex items-center gap-1.5" aria-label="Primary">
          <NavLink href="/chat" active={pathname === "/chat"} icon={<MessageSquareText size={15} />} label="Chat" />
          {isPrivileged && (
            <NavLink href="/admin" active={pathname === "/admin"} icon={<LayoutDashboard size={15} />} label="Admin" />
          )}
          <ThemeToggle />
          <span className="hidden items-center gap-1.5 rounded-full bg-slate-200/60 px-2.5 py-1 text-xs font-semibold text-slate-600 md:inline-flex dark:bg-slate-800 dark:text-slate-300">
            <Sparkles size={12} /> {user?.role}
          </span>
          <button onClick={logout} aria-label="Log out" className="flex h-9 w-9 items-center justify-center rounded-xl text-slate-500 hover:bg-slate-200/60 hover:text-red-500 dark:text-slate-400">
            <LogOut size={16} />
          </button>
        </nav>
      </div>
    </header>
  );
}

function NavLink({ href, active, icon, label }: { href: string; active: boolean; icon: React.ReactNode; label: string }) {
  return (
    <Link
      href={href}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold transition-colors",
        active
          ? "bg-brand-600/10 text-brand-700 dark:bg-brand-500/15 dark:text-brand-200"
          : "text-slate-500 hover:bg-slate-200/60 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100",
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </Link>
  );
}
