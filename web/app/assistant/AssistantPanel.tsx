"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

import {
  AssistantMode,
  AssistantSettings,
  SpeechEngine,
  parseSettings,
  privacyNotice,
  saveSettings,
  serverSettingsSnapshot,
  settingsSnapshot,
  subscribeSettings,
} from "./assistantSettings";
import { ApplyResult, AssistantTaskFields, FIELD_LABEL_KEYS, FilledKey } from "./taskFill";
import { useI18n } from "../i18n/I18nProvider";
import type { TFunction } from "../i18n/translate";
import { AssistantSettingsPanel } from "./AssistantSettingsPanel";
import { useSpeech } from "./useSpeech";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ServerConfig = {
  enabled: boolean;
  llm_configured: boolean;
  llm_local: boolean;
  transcription_configured: boolean;
};

type Turn = { role: "user" | "assistant"; content: string };

type ExtractResponse = {
  fields: AssistantTaskFields;
  missing: string[];
  next_question: string;
  warnings: string[];
};

type Props = {
  /** Valeurs déjà saisies dans le formulaire (POST /assistant/extract -> current_values). */
  values: Record<string, unknown>;
  /** Applique les champs au formulaire ; `overwrite` = l'utilisateur corrige une saisie. */
  onFields: (fields: AssistantTaskFields, overwrite: boolean) => ApplyResult;
};

function labels(keys: FilledKey[], t: TFunction): string {
  return [...new Set(keys.map((key) => t(FIELD_LABEL_KEYS[key])))].join(", ");
}

function speakAloud(text: string, lang: string, onEnd: () => void) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return onEnd();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = lang;
  utterance.onend = onEnd;
  utterance.onerror = onEnd;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utterance);
}

export function AssistantPanel({ values, onFields }: Props) {
  const { t, tag } = useI18n();
  const rawSettings = useSyncExternalStore(subscribeSettings, settingsSnapshot, serverSettingsSnapshot);
  const settings = parseSettings(rawSettings);
  const [config, setConfig] = useState<ServerConfig | null>(null);
  const [configError, setConfigError] = useState(false);
  const [text, setText] = useState("");
  const [history, setHistory] = useState<Turn[]>([]);
  const [question, setQuestion] = useState("");
  const [summary, setSummary] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const settingsRef = useRef(settings);
  const startListeningRef = useRef<() => void>(() => {});
  useEffect(() => {
    settingsRef.current = settings;
  });

  const [showSettings, setShowSettings] = useState(false);
  const assistantOn = config?.enabled === true;
  const [configVersion, setConfigVersion] = useState(0);

  useEffect(() => {
    fetch(`${API_URL}/assistant/config`)
      .then((response) => (response.ok ? (response.json() as Promise<ServerConfig>) : Promise.reject()))
      .then((data) => {
        setConfig(data);
        setConfigError(false);
      })
      .catch(() => setConfigError(true));
  }, [configVersion]);

  function update(patch: Partial<AssistantSettings>) {
    saveSettings({ ...settings, ...patch });
  }

  const submit = useCallback(
    async (transcript: string) => {
      const spoken = transcript.trim();
      if (spoken === "") return;
      setSending(true);
      setError(null);
      try {
        const response = await fetch(`${API_URL}/assistant/extract`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            form: "task",
            transcript: spoken,
            current_values: values,
            history: history.slice(-12),
            mode: settingsRef.current.mode,
          }),
        });
        if (!response.ok) {
          const body = (await response.json().catch(() => ({}))) as { detail?: string };
          return setError(body.detail ?? t("bilans.error.httpStatus", { status: response.status }));
        }
        const result = (await response.json()) as ExtractResponse;
        const applied = onFields(result.fields, overwrite);
        const notes: string[] = [];
        if (applied.filled.length > 0) notes.push(t("assistant.filled", { fields: labels(applied.filled, t) }));
        if (applied.kept.length > 0) {
          notes.push(t("assistant.kept", { fields: labels(applied.kept, t) }));
        }
        if (applied.filled.length === 0 && applied.kept.length === 0) {
          notes.push(t("assistant.understoodNothing"));
        }
        setSummary([...notes, ...result.warnings]);
        const turns: Turn[] = [...history, { role: "user", content: spoken }];
        if (result.next_question) turns.push({ role: "assistant", content: result.next_question });
        setHistory(turns);
        setQuestion(result.next_question);
        setText("");
        if (result.next_question && settingsRef.current.speak) {
          speakAloud(result.next_question, tag, () => {
            if (settingsRef.current.mode === "guided") startListeningRef.current();
          });
        }
      } catch {
        setError(t("assistant.error.unreachable"));
      } finally {
        setSending(false);
      }
    },
    [values, history, onFields, overwrite, t, tag],
  );

  const speech = useSpeech(settings.engine, (spoken) => {
    setText(spoken);
    void submit(spoken);
  });

  useEffect(() => {
    startListeningRef.current = speech.start;
  });

  const input = "rounded border p-2";

  return (
    <section className="flex flex-col gap-3 rounded border border-dashed p-4 text-sm sm:col-span-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 font-medium">
          {t("assistant.title")}
          {config && (
            <span
              className={`rounded px-2 py-0.5 text-xs font-normal ${assistantOn ? "bg-green-100 text-green-900" : "bg-gray-200 text-gray-900"}`}
            >
              {assistantOn ? t("assistant.on") : t("assistant.off")}
            </span>
          )}
        </span>
        <button
          type="button"
          onClick={() => setShowSettings((open) => !open)}
          aria-expanded={showSettings}
          aria-label={t("assistant.settings")}
          title={t("assistant.settingsTitle")}
          className={`rounded border px-2 py-1 text-base leading-none ${showSettings ? "bg-gray-200 text-gray-900" : ""}`}
        >
          ⚙
        </button>
      </div>

      {showSettings && (
        <AssistantSettingsPanel onSaved={() => setConfigVersion((version) => version + 1)} />
      )}

      {configError && (
        <p className="text-red-600">{t("assistant.error.server")}</p>
      )}
      {config && !assistantOn && (
        <p className="text-xs text-gray-600">
          {t("assistant.disabledHelp")}
        </p>
      )}
      {assistantOn && (
        <>
          {!config.llm_configured && (
            <p className="text-amber-700">
              {t("assistant.noModel")}
            </p>
          )}

          {config.llm_configured && (
            <>
              <p className="text-xs text-gray-600">
                {privacyNotice(t, settings.engine, config.llm_local)}
              </p>

              <div className="flex flex-wrap items-center gap-3">
                <label className="flex items-center gap-1">
                  {t("assistant.listen")}
                  <select
                    value={settings.engine}
                    onChange={(e) => update({ engine: e.target.value as SpeechEngine })}
                    className={input}
                  >
                    <option value="browser">{t("assistant.engine.browser")}</option>
                    <option value="server" disabled={!config.transcription_configured}>
                      {t("assistant.engine.server")}
                      {config.transcription_configured ? "" : ` ${t("assistant.engine.notConfigured")}`}
                    </option>
                  </select>
                </label>
                <label className="flex items-center gap-1">
                  {t("assistant.mode")}
                  <select
                    value={settings.mode}
                    onChange={(e) => update({ mode: e.target.value as AssistantMode })}
                    className={input}
                  >
                    <option value="dictation">{t("assistant.mode.dictation")}</option>
                    <option value="guided">{t("assistant.mode.guided")}</option>
                  </select>
                </label>
                <label className="flex items-center gap-1">
                  <input
                    type="checkbox"
                    checked={settings.speak}
                    onChange={(e) => update({ speak: e.target.checked })}
                  />
                  {t("assistant.speak")}
                </label>
              </div>

              {question && (
                <p className="rounded bg-blue-50 p-2 text-gray-900" role="status">
                  {question}
                </p>
              )}

              <div className="flex flex-col gap-2">
                <textarea
                  value={speech.interim !== "" ? `${text} ${speech.interim}` : text}
                  onChange={(e) => setText(e.target.value)}
                  rows={2}
                  placeholder={t("assistant.placeholder")}
                  className={input}
                  aria-label={t("assistant.inputLabel")}
                />
                <div className="flex flex-wrap items-center gap-2">
                  {speech.supported && (
                    <button
                      type="button"
                      onClick={speech.listening ? speech.stop : speech.start}
                      disabled={speech.busy || sending}
                      className={`rounded border px-3 py-1 ${speech.listening ? "border-red-600 text-red-600" : "border-black"}`}
                    >
                      {speech.listening ? t("assistant.stop") : t("assistant.speakButton")}
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void submit(text)}
                    disabled={sending || speech.busy || text.trim() === ""}
                    className="rounded border border-black px-3 py-1 disabled:opacity-50"
                  >
                    {sending ? t("assistant.analysing") : t("assistant.fill")}
                  </button>
                  <label className="flex items-center gap-1 text-xs text-gray-600">
                    <input
                      type="checkbox"
                      checked={overwrite}
                      onChange={(e) => setOverwrite(e.target.checked)}
                    />
                    {t("assistant.overwrite")}
                  </label>
                  {speech.busy && <span className="text-xs text-gray-600">{t("assistant.transcribing")}</span>}
                  {!speech.supported && (
                    <span className="text-xs text-gray-600">
                      {t("assistant.noMic")}
                    </span>
                  )}
                </div>
              </div>

              {(error || speech.error) && <p className="text-red-600">{error ?? speech.error}</p>}
              {summary.length > 0 && (
                <ul className="list-disc pl-5 text-xs text-gray-700">
                  {summary.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              )}
              <p className="text-xs text-gray-500">
                {t("assistant.prefillNote")}
              </p>
            </>
          )}
        </>
      )}
    </section>
  );
}
