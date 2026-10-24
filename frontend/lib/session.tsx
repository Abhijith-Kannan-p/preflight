"use client";

// Demo session: no sign-up. The first visit signs in as abhi1 (Creator); the role switcher
// in the header swaps to any seeded PayWise user instantly with a fresh signed token.

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useSWRConfig } from "swr";

import { api, getToken, post, setToken } from "./api";
import type { UserRef } from "./types";

export const DEFAULT_USER = "usr_abhi1";

interface SessionValue {
  user: UserRef | null;
  permissions: string[];
  ready: boolean;
  error: string | null;
  switchUser: (userId: string) => Promise<void>;
  can: (permission: string) => boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

interface SessionOut {
  token: string;
  user: UserRef;
  permissions: string[];
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { mutate } = useSWRConfig();
  const [user, setUser] = useState<UserRef | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const adopt = useCallback((s: SessionOut) => {
    setToken(s.token);
    setUser(s.user);
    setPermissions(s.permissions);
    setError(null);
  }, []);

  const switchUser = useCallback(
    async (userId: string) => {
      const s = await post<SessionOut>("/api/auth/demo-login", { user_id: userId });
      adopt(s);
      // Every cached view depends on who is looking: revalidate all of them in the background
      // (keeping the current data on screen, so nothing flashes or remounts).
      void mutate(() => true);
    },
    [adopt, mutate],
  );

  useEffect(() => {
    let cancelled = false;
    async function start() {
      try {
        const s = getToken()
          ? await api<SessionOut>("/api/auth/me").catch(() => post<SessionOut>("/api/auth/demo-login", { user_id: DEFAULT_USER }))
          : await post<SessionOut>("/api/auth/demo-login", { user_id: DEFAULT_USER });
        if (!cancelled) adopt(s);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not start the demo session.");
      } finally {
        if (!cancelled) setReady(true);
      }
    }
    void start();
    return () => {
      cancelled = true;
    };
  }, [adopt]);

  const value = useMemo<SessionValue>(
    () => ({ user, permissions, ready, error, switchUser, can: (p) => permissions.includes(p) }),
    [user, permissions, ready, error, switchUser],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession must be used inside SessionProvider");
  return value;
}

export const ROLE_LABEL: Record<string, string> = {
  creator: "Creator",
  reviewer: "Reviewer",
  brand_manager: "Brand Manager",
  approver: "Approver",
  admin: "Admin",
};
