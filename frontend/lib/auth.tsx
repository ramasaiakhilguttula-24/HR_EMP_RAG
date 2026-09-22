"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { User, api } from "./api";

interface AuthCtx {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (full_name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: (u: User) => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    try {
      const t = localStorage.getItem("hr-token");
      const u = localStorage.getItem("hr-user");
      if (t && u) {
        setToken(t);
        setUser(JSON.parse(u));
      }
    } catch {
      /* corrupted storage — start logged out */
    }
    setLoading(false);
  }, []);

  const persist = (t: string, u: User) => {
    localStorage.setItem("hr-token", t);
    localStorage.setItem("hr-user", JSON.stringify(u));
    setToken(t);
    setUser(u);
  };

  const login = useCallback(
    async (email: string, password: string) => {
      const pair = await api.login(email, password);
      // token carries identity; fetch profile via users list? use register-style echo:
      // decode role from token payload (non-verifying, UI hint only)
      const payload = JSON.parse(atob(pair.access_token.split(".")[1]));
      const me: User = {
        id: payload.sub,
        email: payload.email ?? email,
        full_name: payload.email ?? email,
        role: payload.role ?? "employee",
        department: null,
        location: null,
      };
      persist(pair.access_token, me);
      router.push(me.role === "employee" ? "/chat" : "/chat");
    },
    [router],
  );

  const register = useCallback(
    async (full_name: string, email: string, password: string) => {
      await api.register({ full_name, email, password });
      await login(email, password);
    },
    [login],
  );

  const logout = useCallback(async () => {
    try {
      if (token) await api.logout(token);
    } catch {
      /* logout is best-effort */
    }
    localStorage.removeItem("hr-token");
    localStorage.removeItem("hr-user");
    setToken(null);
    setUser(null);
    router.push("/login");
  }, [router, token]);

  const refreshUser = useCallback((u: User) => {
    setUser(u);
    localStorage.setItem("hr-user", JSON.stringify(u));
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, register, logout, refreshUser }),
    [user, token, loading, login, register, logout, refreshUser],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}

export function useRequireAuth(): { user: User; token: string } | null {
  const { user, token, loading } = useAuth();
  const router = useRouter();
  useEffect(() => {
    if (!loading && (!user || !token)) router.replace("/login");
  }, [user, token, loading, router]);
  if (!user || !token) return null;
  return { user, token };
}
