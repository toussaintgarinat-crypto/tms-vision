"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { useAuth } from "./auth/AuthProvider";
import { LanguageSwitcher } from "./i18n/LanguageSwitcher";
import { useI18n } from "./i18n/I18nProvider";
import { NAV_ITEMS, isActive, isMenuHidden } from "./navItems";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Numéro de version de l'application (utile pour savoir ce qui tourne chez un client).
function useAppVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/version`)
      .then((response) => (response.ok ? (response.json() as Promise<{ version: string }>) : null))
      .then((data) => {
        if (!cancelled && data) setVersion(data.version);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return version;
}

type UpdateInfo = { version: string; url: string; installable: boolean };
type UpdateStatus = { step: string; message: string; progress: number | null };

type CheckResult = "upToDate" | "unreachable";

const AUTO_CHECK_MS = 60 * 60 * 1000; // revérification automatique toutes les heures
const FOCUS_CHECK_MS = 10 * 60 * 1000; // et au retour sur la fenêtre, au plus toutes les 10 minutes

// Une version plus récente est publiée (application de bureau seulement : l'API répond
// « available: false, supported: false » ailleurs). Si elle peut s'installer seule (`installable`), un clic
// sauvegarde les données, télécharge, installe et relance l'application ; sinon le lien ouvre la page de
// téléchargement. La recherche se refait seule (toutes les heures, au retour sur la fenêtre) ; `checkNow`
// (bouton des administrateurs) ignore le cache du serveur et dit si GitHub a répondu.
function useUpdate() {
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  const [supported, setSupported] = useState(false);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState<CheckResult | null>(null);
  const lastCheck = useRef(0);

  const run = useCallback(async (force: boolean): Promise<CheckResult | null> => {
    lastCheck.current = Date.now();
    try {
      const response = await fetch(`${API_URL}/update${force ? "?force=true" : ""}`);
      if (!response.ok) return force ? "unreachable" : null;
      const data = (await response.json()) as {
        available: boolean;
        version: string | null;
        url: string | null;
        installable?: boolean;
        reachable?: boolean;
        supported?: boolean;
      };
      setSupported(data.supported === true);
      if (data.available && data.version && data.url) {
        setUpdate({ version: data.version, url: data.url, installable: data.installable === true });
        return null;
      }
      return data.reachable === false ? "unreachable" : "upToDate";
    } catch {
      return force ? "unreachable" : null;
    }
  }, []);

  useEffect(() => {
    void run(false);
    const timer = setInterval(() => void run(false), AUTO_CHECK_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - lastCheck.current > FOCUS_CHECK_MS) {
        void run(false);
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [run]);

  useEffect(() => {
    if (!result) return;
    const timer = setTimeout(() => setResult(null), 6000);
    return () => clearTimeout(timer);
  }, [result]);

  const checkNow = useCallback(async () => {
    setChecking(true);
    setResult(null);
    const outcome = await run(true);
    setChecking(false);
    setResult(outcome);
  }, [run]);

  return { update, supported, checking, result, checkNow };
}

function UpdateBanner({ update }: { update: UpdateInfo }) {
  const { t } = useI18n();
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const [restarting, setRestarting] = useState(false);

  useEffect(() => {
    if (!status || !["backup", "download", "install"].includes(status.step)) return;
    const timer = setInterval(() => {
      fetch(`${API_URL}/update/status`)
        .then((response) => (response.ok ? (response.json() as Promise<UpdateStatus>) : null))
        .then((data) => data && setStatus(data))
        // L'application s'est fermée pour s'installer : la réponse n'arrive plus.
        .catch(() => setRestarting(true));
    }, 700);
    return () => clearInterval(timer);
  }, [status]);

  // L'application est fermée pour s'installer : on attend qu'elle réponde de nouveau, puis on recharge
  // la page (sinon elle reste sur « Installation en cours » même une fois l'application relancée).
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!restarting) return;
    const startedAt = Date.now();
    const timer = setInterval(() => {
      fetch(`${API_URL}/version`)
        .then((response) => {
          if (response.ok) window.location.reload();
        })
        .catch(() => {
          if (Date.now() - startedAt > 3 * 60 * 1000) setSlow(true);
        });
    }, 2000);
    return () => clearInterval(timer);
  }, [restarting]);

  const install = () => {
    setStatus({ step: "backup", message: t("update.preparing"), progress: null });
    fetch(`${API_URL}/update/install`, { method: "POST" })
      .then((response) => (response.ok ? (response.json() as Promise<UpdateStatus>) : Promise.reject()))
      .then(setStatus)
      .catch(() =>
        setStatus({ step: "error", message: t("update.failedToStart"), progress: null }),
      );
  };

  const className =
    "rounded-full bg-amber-100 px-3 py-0.5 text-xs font-medium text-amber-900 hover:bg-amber-200";
  if (restarting) {
    return (
      <span className={className} role="status">
        {t(slow ? "update.slow" : "update.restarting")}
      </span>
    );
  }
  if (status && status.step !== "error") {
    const percent = status.progress === null ? "" : ` ${Math.round(status.progress * 100)} %`;
    return (
      <span className={className} role="status">
        {status.message}
        {percent}
      </span>
    );
  }
  if (update.installable) {
    return (
      <>
        <button type="button" onClick={install} className={className}>
          {t("update.install", { version: update.version })}
        </button>
        {status && <span className="text-xs text-red-700">{status.message}</span>}
      </>
    );
  }
  return (
    <a href={update.url} target="_blank" rel="noopener noreferrer" className={className}>
      {t("update.download", { version: update.version })}
    </a>
  );
}

// Barre du haut avec un menu rétractable : accès à toutes les pages sans taper l'adresse.
export function NavMenu() {
  const { t } = useI18n();
  const { user, status, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const appVersion = useAppVersion();
  const { update, supported, checking, result, checkNow } = useUpdate();
  // Le bouton est réservé aux administrateurs (ou ouvert à tous si l'application n'a pas de comptes).
  const canCheck =
    supported && status !== null && (!status.auth_required || (user?.roles.includes("administrateur") ?? false));

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  if (isMenuHidden(pathname)) return null;

  return (
    <>
      <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-zinc-200 bg-background/90 px-4 py-2 backdrop-blur dark:border-zinc-700">
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="navigation-principale"
          className="flex items-center gap-2 rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium hover:bg-zinc-100 dark:border-zinc-600 dark:hover:bg-zinc-800"
        >
          <span aria-hidden="true">☰</span> {t("nav.menu")}
        </button>
        <span className="text-sm font-semibold">TMS Vision</span>
        {appVersion && <span className="text-xs text-zinc-500" title={t("nav.versionTitle")}>v{appVersion}</span>}
        {canCheck && (
          <button
            type="button"
            onClick={() => void checkNow()}
            disabled={checking}
            className="text-xs text-zinc-500 underline hover:text-zinc-800 disabled:no-underline dark:hover:text-zinc-200"
          >
            {t(checking ? "update.checking" : "update.check")}
          </button>
        )}
        {result && (
          <span
            role="status"
            className={`text-xs ${result === "unreachable" ? "text-red-700" : "text-green-700"}`}
          >
            {t(result === "upToDate" ? "update.upToDate" : "update.unreachable")}
          </span>
        )}
        {update && <UpdateBanner update={update} />}
        <LanguageSwitcher className="ml-auto" />
        {user && (
          <Link href="/compte" className="text-sm underline" title={user.email}>
            {user.name}
          </Link>
        )}
      </header>

      {open && (
        <>
          <button
            type="button"
            aria-label={t("nav.closeMenu")}
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default bg-black/30"
          />
          <nav
            id="navigation-principale"
            aria-label={t("nav.main")}
            className="fixed left-0 top-0 z-50 flex h-full w-72 max-w-[85vw] flex-col gap-1 border-r border-zinc-200 bg-background p-4 shadow-xl dark:border-zinc-700"
          >
            <div className="mb-3 flex items-center justify-between">
              <span className="text-sm font-semibold">TMS Vision</span>
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  buttonRef.current?.focus();
                }}
                aria-label={t("nav.closeMenu")}
                className="rounded px-2 py-1 text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              >
                ✕
              </button>
            </div>
            {NAV_ITEMS.map((item) => {
              const active = isActive(pathname, item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={() => setOpen(false)}
                  aria-current={active ? "page" : undefined}
                  className={`rounded-lg px-3 py-2 text-sm ${
                    active ? "bg-blue-600 font-semibold text-white" : "hover:bg-zinc-100 dark:hover:bg-zinc-800"
                  }`}
                >
                  {t(item.labelKey)}
                </Link>
              );
            })}
            {user && (
              <div className="mt-auto flex flex-col gap-1 border-t border-zinc-200 pt-3 dark:border-zinc-700">
                {[
                  { href: "/compte", label: t("nav.account"), show: true },
                  { href: "/fiches", label: t("nav.sheets"), show: true },
                  { href: "/validation", label: t("nav.review"), show: user.roles.includes("osteopathe") },
                  { href: "/administration", label: t("nav.admin"), show: user.roles.includes("administrateur") },
                ]
                  .filter((entry) => entry.show)
                  .map((entry) => (
                    <Link
                      key={entry.href}
                      href={entry.href}
                      onClick={() => setOpen(false)}
                      className="rounded-lg px-3 py-2 text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                    >
                      {entry.label}
                    </Link>
                  ))}
                <button
                  type="button"
                  onClick={() => {
                    setOpen(false);
                    void logout();
                  }}
                  className="rounded-lg px-3 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800"
                >
                  {t("auth.logout")}
                </button>
              </div>
            )}
          </nav>
        </>
      )}
    </>
  );
}
