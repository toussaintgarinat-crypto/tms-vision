"use client";

import { createContext, useContext, useEffect, useMemo, useSyncExternalStore, type ReactNode } from "react";
import { translator } from "./catalog";
import { DEFAULT_LOCALE, LOCALE_TAGS, STORAGE_KEY, detectLocale, type Locale } from "./locales";
import type { Vars } from "./translate";

type I18n = {
  locale: Locale;
  // Étiquette BCP 47 de la langue (« fr-FR »), pour les dates, les nombres et la voix.
  tag: string;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Vars) => string;
};

const FALLBACK: I18n = {
  locale: DEFAULT_LOCALE,
  tag: LOCALE_TAGS[DEFAULT_LOCALE],
  setLocale: () => {},
  t: translator(DEFAULT_LOCALE),
};

const I18nContext = createContext<I18n>(FALLBACK);

// La langue vit hors de React (stockage du navigateur) : on s'y abonne avec useSyncExternalStore,
// qui rend toujours la langue par défaut côté serveur et à l'hydratation, puis la vraie langue.
const listeners = new Set<() => void>();
let remembered: Locale | null = null; // repli quand le stockage du navigateur est indisponible

function currentLocale(): Locale {
  let stored: string | null = remembered;
  if (!stored) {
    try {
      stored = window.localStorage.getItem(STORAGE_KEY);
    } catch {
      // Navigation privée ou stockage bloqué : on se rabat sur la langue du navigateur.
    }
  }
  return detectLocale(stored, navigator.languages ?? [navigator.language]);
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener); // choix fait dans un autre onglet
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function chooseLocale(next: Locale): void {
  remembered = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Le choix vaut pour cette visite seulement.
  }
  listeners.forEach((listener) => listener());
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const locale = useSyncExternalStore(subscribe, currentLocale, () => DEFAULT_LOCALE);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18n>(
    () => ({
      locale,
      tag: LOCALE_TAGS[locale],
      setLocale: chooseLocale,
      t: translator(locale),
    }),
    [locale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
