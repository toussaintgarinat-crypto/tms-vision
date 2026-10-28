"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
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

// Une version plus récente est publiée (application de bureau seulement : l'API répond
// « available: false » ailleurs). Si elle peut s'installer seule (`installable`), un clic sauvegarde
// les données, télécharge, installe et relance l'application ; sinon le lien ouvre la page de téléchargement.
function useUpdate(): UpdateInfo | null {
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/update`)
      .then((response) =>
        response.ok
          ? (response.json() as Promise<{
              available: boolean;
              version: string | null;
              url: string | null;
              installable?: boolean;
            }>)
          : null,
      )
      .then((data) => {
        if (!cancelled && data?.available && data.version && data.url) {
          setUpdate({ version: data.version, url: data.url, installable: data.installable === true });
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);
  return update;
}

function UpdateBanner({ update }: { update: UpdateInfo }) {
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

  const install = () => {
    setStatus({ step: "backup", message: "Préparation…", progress: null });
    fetch(`${API_URL}/update/install`, { method: "POST" })
      .then((response) => (response.ok ? (response.json() as Promise<UpdateStatus>) : Promise.reject()))
      .then(setStatus)
      .catch(() =>
        setStatus({ step: "error", message: "La mise à jour n'a pas pu démarrer.", progress: null }),
      );
  };

  const className =
    "rounded-full bg-amber-100 px-3 py-0.5 text-xs font-medium text-amber-900 hover:bg-amber-200";
  if (restarting) {
    return (
      <span className={className} role="status">
        Installation en cours : l&apos;application va se rouvrir toute seule. Rechargez cette page dans une minute.
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
          Nouvelle version {update.version} disponible : mettre à jour (données conservées)
        </button>
        {status && <span className="text-xs text-red-700">{status.message}</span>}
      </>
    );
  }
  return (
    <a href={update.url} target="_blank" rel="noopener noreferrer" className={className}>
      Nouvelle version {update.version} disponible : télécharger
    </a>
  );
}

// Barre du haut avec un menu rétractable : accès à toutes les pages sans taper l'adresse.
export function NavMenu() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const appVersion = useAppVersion();
  const update = useUpdate();

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
          <span aria-hidden="true">☰</span> Menu
        </button>
        <span className="text-sm font-semibold">TMS Vision</span>
        {appVersion && <span className="text-xs text-zinc-500" title="Version de l'application">v{appVersion}</span>}
        {update && <UpdateBanner update={update} />}
      </header>

      {open && (
        <>
          <button
            type="button"
            aria-label="Fermer le menu"
            tabIndex={-1}
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 cursor-default bg-black/30"
          />
          <nav
            id="navigation-principale"
            aria-label="Navigation principale"
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
                aria-label="Fermer le menu"
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
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </>
      )}
    </>
  );
}
