"use client";

import { useEffect, useState } from "react";
import { ShieldCheck } from "lucide-react";
import { User, api } from "@/lib/api";
import { Badge, EmptyState, Spinner, useToast } from "@/components/ui";

const ROLES = ["employee", "hr_manager", "department_head", "legal_counsel", "admin"];

export function UserManager({ token }: { token: string }) {
  const { push } = useToast();
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.users(token).then(setUsers).catch(() => setUsers([])).finally(() => setLoading(false));
  };
  useEffect(load, [token]);

  const setRole = async (u: User, role: string) => {
    try {
      const updated = await api.setRole(token, u.id, role);
      setUsers((xs) => xs.map((x) => (x.id === u.id ? updated : x)));
      push("ok", `${u.email} → ${role}`);
    } catch {
      push("err", "Role update failed (admin only).");
    }
  };

  if (loading) return <p className="flex items-center gap-2 p-6 text-sm text-slate-500"><Spinner /> Loading users…</p>;
  if (!users.length) return <EmptyState icon={<ShieldCheck size={22} />} title="No users" hint="Registered employees appear here." />;

  return (
    <ul className="divide-y divide-slate-200/70 dark:divide-slate-800">
      {users.map((u) => (
        <li key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{u.full_name || u.email}</p>
            <p className="truncate text-xs text-slate-500">{u.email}{u.department ? ` · ${u.department}` : ""}{u.location ? ` · ${u.location}` : ""}</p>
          </div>
          <Badge tone={u.role === "admin" ? "red" : u.role === "employee" ? "slate" : "brand"}>{u.role}</Badge>
          <label className="sr-only" htmlFor={`role-${u.id}`}>Role for {u.email}</label>
          <select
            id={`role-${u.id}`}
            value={u.role}
            onChange={(e) => setRole(u, e.target.value)}
            className="rounded-lg border border-slate-300 bg-white/80 px-2 py-1.5 text-xs dark:border-slate-700 dark:bg-slate-900/80"
          >
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </li>
      ))}
    </ul>
  );
}
