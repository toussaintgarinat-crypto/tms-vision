"use client";

import { LOCALES, LOCALE_LABELS, isLocale } from "./locales";
import { useI18n } from "./I18nProvider";

export function LanguageSwitcher({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();
  return (
    <select
      value={locale}
      onChange={(event) => isLocale(event.target.value) && setLocale(event.target.value)}
      aria-label={t("language.label")}
      className={`rounded-lg border border-zinc-300 bg-transparent px-2 py-1 text-xs dark:border-zinc-600 ${className}`}
    >
      {LOCALES.map((code) => (
        <option key={code} value={code} lang={code}>
          {LOCALE_LABELS[code]}
        </option>
      ))}
    </select>
  );
}
