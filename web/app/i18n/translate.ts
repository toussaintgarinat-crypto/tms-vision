import { DEFAULT_LOCALE, type Locale } from "./locales";

export type Messages = Record<string, string>;
export type Vars = Record<string, string | number>;

// Remplace `{nom}` par la valeur donnée ; un marqueur sans valeur reste tel quel (on voit l'oubli
// à l'écran plutôt qu'un trou).
export function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (marker, name: string) =>
    name in vars ? String(vars[name]) : marker,
  );
}

// Texte d'une clé dans la langue demandée ; à défaut, dans la langue de référence (le français) ;
// à défaut, la clé elle-même, pour qu'un oubli saute aux yeux.
export function translate(
  catalog: Record<Locale, Messages>,
  locale: Locale,
  key: string,
  vars?: Vars,
): string {
  const template = catalog[locale]?.[key] ?? catalog[DEFAULT_LOCALE]?.[key] ?? key;
  return interpolate(template, vars);
}
