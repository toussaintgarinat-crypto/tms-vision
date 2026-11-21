import type { TFunction } from "../i18n/translate";

export type SpeechEngine = "browser" | "server";
export type AssistantMode = "dictation" | "guided";

/** Préférences de ce navigateur. L'activation de l'assistant, elle, est réglée sur le serveur. */
export type AssistantSettings = {
  engine: SpeechEngine;
  speak: boolean;
  mode: AssistantMode;
};

export const DEFAULT_SETTINGS: AssistantSettings = {
  engine: "browser",
  speak: false,
  mode: "dictation",
};

export const SETTINGS_KEY = "tms-assistant-settings";

/** Relit des réglages enregistrés ; toute valeur inattendue retombe sur le défaut. */
export function parseSettings(raw: string | null): AssistantSettings {
  if (raw === null) return DEFAULT_SETTINGS;
  try {
    const data = JSON.parse(raw) as Record<string, unknown>;
    return {
      engine: data.engine === "server" ? "server" : "browser",
      speak: data.speak === true,
      mode: data.mode === "guided" ? "guided" : "dictation",
    };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

// Petit magasin : le stockage du navigateur est une source externe (useSyncExternalStore).
// Si le stockage est refusé, les réglages restent en mémoire le temps de la page.
let memoryRaw: string | null = null;
const listeners = new Set<() => void>();

export function subscribeSettings(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Texte brut des réglages (une chaîne est un instantané stable pour React). */
export function settingsSnapshot(): string | null {
  try {
    return window.localStorage.getItem(SETTINGS_KEY) ?? memoryRaw;
  } catch {
    return memoryRaw;
  }
}

export function serverSettingsSnapshot(): string | null {
  return null;
}

export function saveSettings(settings: AssistantSettings): void {
  const raw = JSON.stringify(settings);
  memoryRaw = raw;
  try {
    window.localStorage.setItem(SETTINGS_KEY, raw);
  } catch {
    // stockage indisponible : la copie en mémoire suffit pour cette page.
  }
  listeners.forEach((listener) => listener());
}

/** Phrase de confidentialité à afficher selon les moteurs réellement utilisés. */
export function privacyNotice(t: TFunction, engine: SpeechEngine, llmLocal: boolean): string {
  const ear = t(engine === "browser" ? "assistant.privacy.browser" : "assistant.privacy.server");
  const brain = t(llmLocal ? "assistant.privacy.local" : "assistant.privacy.remote");
  return `${ear} ${brain} ${t("assistant.privacy.noNames")}`;
}
