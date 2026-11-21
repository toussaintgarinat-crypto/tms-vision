// Langues de l'interface. Ajouter une langue : l'ajouter ici, créer `messages/<code>.json`
// (mêmes clés que `fr.json`) et la déclarer dans `catalog.ts`. Le test `messages.test.ts` échoue
// tant qu'une clé manque.
export const LOCALES = ["fr", "en"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "fr";

// Nom de chaque langue dans sa propre langue (c'est ce que le sélecteur affiche).
export const LOCALE_LABELS: Record<Locale, string> = {
  fr: "Français",
  en: "English",
};

// Étiquette BCP 47 pour les dates, les nombres et la voix du navigateur.
export const LOCALE_TAGS: Record<Locale, string> = {
  fr: "fr-FR",
  en: "en-GB",
};

export const STORAGE_KEY = "tms.locale";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

// Langue à utiliser : le choix enregistré s'il existe, sinon la première langue du navigateur
// que l'application sait afficher (« en-US » donne « en »), sinon le français.
export function detectLocale(stored: string | null, browserLanguages: readonly string[]): Locale {
  if (isLocale(stored)) return stored;
  for (const language of browserLanguages) {
    const base = language.toLowerCase().split("-")[0];
    if (isLocale(base)) return base;
  }
  return DEFAULT_LOCALE;
}
