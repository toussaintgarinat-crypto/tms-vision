export type SpeechEngine = "browser" | "server";
export type AssistantMode = "dictation" | "guided";

export type AssistantSettings = {
  enabled: boolean;
  engine: SpeechEngine;
  speak: boolean;
  mode: AssistantMode;
};

/** L'assistant est éteint tant que l'utilisateur ne l'a pas activé. */
export const DEFAULT_SETTINGS: AssistantSettings = {
  enabled: false,
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
      enabled: data.enabled === true,
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
export function privacyNotice(engine: SpeechEngine, llmLocal: boolean): string {
  const ear =
    engine === "browser"
      ? "La dictée passe par le service de reconnaissance vocale de votre navigateur (souvent un serveur distant)."
      : "L'enregistrement est envoyé au service de transcription configuré sur ce serveur.";
  const brain = llmLocal
    ? "Le texte est analysé par un modèle local : il ne quitte pas la machine."
    : "Le texte dicté est envoyé au modèle d'IA configuré sur ce serveur.";
  return `${ear} ${brain} Ne dictez pas de nom ni de donnée permettant d'identifier le salarié.`;
}
