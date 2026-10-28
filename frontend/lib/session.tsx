"use client";

// Demo session: no sign-up. The first visit opens a private sandbox (a copy of the PayWise
// workspace, kept in an httpOnly cookie) and signs in as abhi1 (Creator); the role switcher
// in the header swaps to any of the sandbox's personas instantly with a fresh signed token.

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useSWRConfig } from "swr";

import { ApiError, SESSION_EXPIRED, sandboxCall, setToken } from "./api";
import type { UserRef } from "./types";

export const DEFAULT_USER = "usr_abhi1";
const USER_KEY = "preflight.user";

/** Sandbox members are copies of template personas with a suffix: usr_abhi4_1a2b3c4d. */
const persona = (userId: string) => userId.replace(/_[0-9a-f]{8}$/, "");

interface SessionValue {
  user: UserRef | null;
  permissions: string[];
  workspaceId: string | null;
  ready: boolean;
  error: string | null;
  switchUser: (userId: string) => Promise<void>;
  resetSandbox: () => Promise<void>;
  can: (permission: string) => boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

interface SessionOut {
  token: string;
  user: UserRef;
  permissions: string[];
  workspace_id: string;
  created: boolean;
}

function rememberedUser(): string {
  try {
    return window.localStorage.getItem(USER_KEY) ?? DEFAULT_USER;
  } catch {
    return DEFAULT_USER;
  }
}

function remember(userId: string): void {
  try {
    window.localStorage.setItem(USER_KEY, userId);
  } catch {
    // Private mode: the choice lasts for this page only.
  }
}

const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const { mutate } = useSWRConfig();
  const [user, setUser] = useState<UserRef | null>(null);
  const [permissions, setPermissions] = useState<string[]>([]);
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const opening = useRef<{ userId: string; done: Promise<void> } | null>(null);

  const adopt = useCallback((s: SessionOut) => {
    setToken(s.token);
    remember(persona(s.user.id));
    setUser(s.user);
    setPermissions(s.permissions);
    setWorkspaceId(s.workspace_id);
    setError(null);
  }, []);

  /** Open (or resume) the sandbox. A sleeping free-tier backend can take a while to wake,
   * so network failures and 5xx answers are retried with backoff for about 90 seconds.
   * Calls queue up: switching user while the first session is still opening waits for it
   * and then switches, instead of being dropped. */
  const open = useCallback(
    (userId: string): Promise<void> => {
      const pending = opening.current;
      if (pending?.userId === userId) return pending.done;
      const run = async () => {
        if (pending) await pending.done.catch(() => undefined);
        let delay = 1500;
        for (let attempt = 0; ; attempt++) {
          try {
            adopt(await sandboxCall<SessionOut>("session", { user_id: userId }));
            return;
          } catch (e) {
            const retryable = e instanceof ApiError && (e.status === 0 || e.status >= 500);
            if (!retryable || attempt >= 8) {
              // An unknown persona (e.g. after a reset) falls back to the default user once.
              if (e instanceof ApiError && e.status === 404 && userId !== DEFAULT_USER) {
                adopt(await sandboxCall<SessionOut>("session", { user_id: DEFAULT_USER }));
                return;
              }
              throw e;
            }
            await wait(delay);
            delay = Math.min(delay * 1.6, 15_000);
          }
        }
      };
      const done = run().finally(() => {
        if (opening.current?.done === done) opening.current = null;
      });
      opening.current = { userId, done };
      return done;
    },
    [adopt],
  );

  const switchUser = useCallback(
    async (userId: string) => {
      await open(userId);
      // Every cached view depends on who is looking: revalidate all of them in the background
      // (keeping the current data on screen, so nothing flashes or remounts).
      void mutate(() => true);
    },
    [open, mutate],
  );

  const resetSandbox = useCallback(async () => {
    adopt(await sandboxCall<SessionOut>("reset", { user_id: persona(user?.id ?? DEFAULT_USER) }));
    void mutate(() => true);
  }, [adopt, mutate, user]);

  useEffect(() => {
    let cancelled = false;
    open(rememberedUser())
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Could not open your demo workspace.");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // The sandbox expired (24 h idle) or was reset in another tab: open a fresh one.
  useEffect(() => {
    const onExpired = () => {
      void open(rememberedUser()).then(() => mutate(() => true));
    };
    window.addEventListener(SESSION_EXPIRED, onExpired);
    return () => window.removeEventListener(SESSION_EXPIRED, onExpired);
  }, [open, mutate]);

  const value = useMemo<SessionValue>(
    () => ({ user, permissions, workspaceId, ready, error, switchUser, resetSandbox, can: (p) => permissions.includes(p) }),
    [user, permissions, workspaceId, ready, error, switchUser, resetSandbox],
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
