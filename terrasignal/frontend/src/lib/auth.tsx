"use client";

/** Client-side auth context for the demo. Holds the JWT + decoded identity in
 * localStorage so a refresh keeps the session. RBAC is enforced server-side on
 * every request; the role here only drives UX (hiding admin-only controls). */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { apiFetch, clearToken, getToken, setToken, type Schemas } from "@/lib/api/client";

type LoginResponse = Schemas["LoginResponse"];
export type Identity = Pick<LoginResponse, "username" | "role" | "name">;

const USER_KEY = "terrasignal_user";

interface AuthState {
  user: Identity | null;
  ready: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<Identity | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const raw = typeof window !== "undefined" ? window.localStorage.getItem(USER_KEY) : null;
    if (raw && getToken()) {
      try {
        setUser(JSON.parse(raw) as Identity);
      } catch {
        clearToken();
      }
    }
    setReady(true);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      auth: false,
      body: { username, password },
    });
    setToken(res.token);
    const identity: Identity = { username: res.username, role: res.role, name: res.name };
    window.localStorage.setItem(USER_KEY, JSON.stringify(identity));
    setUser(identity);
  }, []);

  const logout = useCallback(() => {
    clearToken();
    window.localStorage.removeItem(USER_KEY);
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({ user, ready, login, logout }),
    [user, ready, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

const ROLE_RANK: Record<string, number> = { analyst: 1, approver: 2, admin: 3 };

export function hasRole(user: Identity | null, minimum: string): boolean {
  if (!user) return false;
  return (ROLE_RANK[user.role] ?? 0) >= (ROLE_RANK[minimum] ?? 99);
}
