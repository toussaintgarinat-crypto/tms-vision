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

// Barre du haut avec un menu rétractable : accès à toutes les pages sans taper l'adresse.
export function NavMenu() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const appVersion = useAppVersion();

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
