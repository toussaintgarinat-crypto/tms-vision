"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { API_URL, AuthStatus, AuthUser, installAuthFetch, mustLogIn, onUnauthorized } from "./authFetch";

installAuthFetch();

type Auth = {
  status: AuthStatus | null;
  user: AuthUser | null;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<Auth>({ status: null, user: null, refresh: async () => {}, logout: async () => {} });

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [status, setStatus] = useState<AuthStatus | null>(null);

  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/auth/status`);
      if (response.ok) setStatus((await response.json()) as AuthStatus);
    } catch {
      // Serveur injoignable : on garde l'état connu, les pages affichent leurs propres erreurs.
    }
  }, []);

  // Relu à chaque changement de page : la session a pu expirer ou être fermée ailleurs.
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/auth/status`)
      .then((response) => (response.ok ? (response.json() as Promise<AuthStatus>) : null))
      .then((data) => {
        if (!cancelled && data) setStatus(data);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  // Une réponse 401 (session expirée) : on relit l'état, ce qui renvoie vers la connexion.
  useEffect(() => {
    onUnauthorized(() => void refresh());
    return () => onUnauthorized(null);
  }, [refresh]);

  useEffect(() => {
    if (mustLogIn(status, pathname)) router.replace("/connexion");
  }, [status, pathname, router]);

  const logout = useCallback(async () => {
    await fetch(`${API_URL}/auth/logout`, { method: "POST" }).catch(() => {});
    await refresh();
    router.replace("/connexion");
  }, [refresh, router]);

  const value = useMemo<Auth>(() => ({ status, user: status?.user ?? null, refresh, logout }), [status, refresh, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): Auth {
  return useContext(AuthContext);
}
