import type { Locale } from "./locales";
import type { Messages } from "./translate";
import en from "./messages/en.json";
import fr from "./messages/fr.json";

export const CATALOG: Record<Locale, Messages> = { fr, en };
