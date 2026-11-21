import type { Locale } from "./locales";
import { translate, type Messages, type TFunction } from "./translate";
import en from "./messages/en.json";
import fr from "./messages/fr.json";

export const CATALOG: Record<Locale, Messages> = { fr, en };

// Traducteur d'une langue donnée (hors React : tests, fonctions pures).
export function translator(locale: Locale): TFunction {
  return (key, vars) => translate(CATALOG, locale, key, vars);
}
