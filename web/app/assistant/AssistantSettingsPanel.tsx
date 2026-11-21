"use client";

import { useEffect, useState } from "react";

import { useI18n } from "../i18n/I18nProvider";
import type { TFunction } from "../i18n/translate";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Provider = {
  id: string;
  label: string;
  base_url: string;
  local: boolean;
  key_required: boolean;
  hint: string;
};

type ServerSettings = {
  enabled: boolean;
  provider: string;
  base_url: string;
  model: string;
  key_set: boolean;
  key_env: string;
  transcription_url: string;
  transcription_key_set: boolean;
  transcription_key_env: string;
  providers: Provider[];
};

type Props = {
  /** Appelé après un enregistrement réussi (le bandeau relit la configuration du serveur). */
  onSaved: () => void;
};

async function detail(response: Response, t: TFunction): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  return body.detail ?? t("bilans.error.httpStatus", { status: response.status });
}

export function AssistantSettingsPanel({ onSaved }: Props) {
  const { t } = useI18n();
  const [server, setServer] = useState<ServerSettings | null>(null);
  const [provider, setProvider] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [transcriptionUrl, setTranscriptionUrl] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelsStatus, setModelsStatus] = useState<"idle" | "loading" | "ok" | "error">("idle");
  const [modelsMessage, setModelsMessage] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/assistant/settings`)
      .then((response) => (response.ok ? (response.json() as Promise<ServerSettings>) : Promise.reject()))
      .then((data) => {
        setServer(data);
        setProvider(data.provider);
        setBaseUrl(data.base_url);
        setModel(data.model);
        setTranscriptionUrl(data.transcription_url);
      })
      .catch(() => setMessage({ ok: false, text: t("assistantSettings.error.read") }));
  }, [t]);

  // La liste des modèles se charge toute seule dès que le fournisseur et l'adresse sont connus.
  const [reload, setReload] = useState(0);
  useEffect(() => {
    if (server === null || provider === "" || baseUrl.trim() === "") return;
    let cancelled = false;
    const timer = setTimeout(() => {
      setModelsStatus("loading");
      fetch(`${API_URL}/assistant/settings/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider, base_url: baseUrl }),
      })
        .then((response) =>
          response.ok
            ? (response.json() as Promise<{ ok: boolean; message: string; models: string[] }>)
            : Promise.reject(),
        )
        .then((result) => {
          if (cancelled) return;
          setModels(result.models);
          setModelsStatus(result.ok ? "ok" : "error");
          setModelsMessage(result.message);
        })
        .catch(() => {
          if (cancelled) return;
          setModels([]);
          setModelsStatus("error");
          setModelsMessage(t("assistantSettings.error.unreachable"));
        });
    }, 400);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [server, provider, baseUrl, reload, t]);

  if (server === null) {
    return <p className="text-xs text-gray-600">{message?.text ?? t("assistantSettings.loading")}</p>;
  }

  const current = server.providers.find((p) => p.id === provider);

  function chooseProvider(id: string) {
    setProvider(id);
    const next = server?.providers.find((p) => p.id === id);
    setBaseUrl(next?.base_url ?? "");
    setModel("");
    setModels([]);
    setModelsStatus("idle");
    setMessage(null);
  }

  async function save() {
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/assistant/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider,
          base_url: baseUrl,
          model,
          transcription_url: transcriptionUrl,
        }),
      });
      if (!response.ok) return setMessage({ ok: false, text: await detail(response, t) });
      setServer((await response.json()) as ServerSettings);
      setMessage({ ok: true, text: t("assistantSettings.saved") });
      onSaved();
    } catch {
      setMessage({ ok: false, text: t("assistantSettings.error.save") });
    } finally {
      setSaving(false);
    }
  }

  async function toggleEnabled(next: boolean) {
    setSaving(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/assistant/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: next }),
      });
      if (!response.ok) return setMessage({ ok: false, text: await detail(response, t) });
      setServer((await response.json()) as ServerSettings);
      onSaved();
    } catch {
      setMessage({ ok: false, text: t("assistantSettings.error.toggle") });
    } finally {
      setSaving(false);
    }
  }

  const input = "rounded border p-2";
  const missingKey = current?.key_required === true && !server.key_set;

  return (
    <div className="flex flex-col gap-3 rounded border bg-gray-50 p-3 text-gray-900 dark:bg-transparent dark:text-inherit">
      <h4 className="font-semibold">{t("assistant.settings")}</h4>
      <label className="flex items-center gap-2 font-medium">
        <input
          type="checkbox"
          checked={server.enabled}
          disabled={saving}
          onChange={(e) => void toggleEnabled(e.target.checked)}
        />
        {t("assistantSettings.enabled")}
        <span className={`text-xs font-normal ${server.enabled ? "text-green-700" : "text-gray-600"}`}>
          {server.enabled ? t("assistantSettings.enabledHelp") : t("assistantSettings.disabledHelp")}
        </span>
      </label>

      <label className="flex flex-col gap-1">
        {t("assistantSettings.provider")}
        <select value={provider} onChange={(e) => chooseProvider(e.target.value)} className={input}>
          <option value="">{t("bilan.attach.choose")}</option>
          {server.providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        {current && <span className="text-xs text-gray-600">{current.hint}</span>}
      </label>

      <label className="flex flex-col gap-1">
        {t("assistantSettings.address")}
        <input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="http://localhost:11434/v1"
          className={input}
        />
        {current?.local && (
          <span className="text-xs text-gray-600">
            {t("assistantSettings.docker")}
          </span>
        )}
      </label>

      {current && (current.key_required || provider === "custom") && (
        <div className="text-xs" role="status">
          {server.key_set ? (
            <span className="text-green-700">{t("assistantSettings.keyFound", { env: server.key_env })}</span>
          ) : (
            <span className={missingKey ? "text-amber-700" : "text-gray-600"}>
              {t(missingKey ? "assistantSettings.keyMissing" : "assistantSettings.keyOptional")}{" "}
              {t("assistantSettings.keyHowTo", { env: server.key_env })}
            </span>
          )}
        </div>
      )}

      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <label htmlFor="assistant-model">{t("assistantSettings.model")}</label>
          {modelsStatus === "loading" && <span className="text-xs text-gray-600">{t("assistantSettings.modelsLoading")}</span>}
          {provider !== "" && modelsStatus !== "loading" && (
            <button
              type="button"
              onClick={() => setReload((n) => n + 1)}
              className="text-xs text-blue-600 underline"
            >
              {t("assistantSettings.refresh")}
            </button>
          )}
        </div>
        <select
          id="assistant-model"
          value={model}
          onChange={(e) => setModel(e.target.value)}
          disabled={provider === ""}
          className={input}
        >
          <option value="">{t("assistantSettings.modelAuto")}</option>
          {model !== "" && !models.includes(model) && <option value={model}>{model}</option>}
          {models.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
        {provider === "" && <span className="text-xs text-gray-600">{t("assistantSettings.chooseProviderFirst")}</span>}
        {modelsStatus !== "idle" && modelsStatus !== "loading" && (
          <span className={`text-xs ${modelsStatus === "ok" ? "text-green-700" : "text-red-600"}`} role="status">
            {modelsMessage}
          </span>
        )}
      </div>

      <details className="rounded border p-2">
        <summary className="cursor-pointer">{t("assistantSettings.transcription")}</summary>
        <div className="mt-2 flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            {t("assistantSettings.transcriptionAddress")}
            <input
              value={transcriptionUrl}
              onChange={(e) => setTranscriptionUrl(e.target.value)}
              placeholder="http://localhost:5700"
              className={input}
            />
          </label>
          <p className="text-xs text-gray-600">
            {server.transcription_key_set
              ? t("assistantSettings.transcriptionKeyFound", { env: server.transcription_key_env })
              : t("assistantSettings.transcriptionKeyHowTo", { env: server.transcription_key_env })}
          </p>
        </div>
      </details>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving || provider === ""}
          className="rounded border border-black px-3 py-1 disabled:opacity-50"
        >
          {t("common.save")}
        </button>
        {message && (
          <span className={message.ok ? "text-green-700" : "text-red-600"} role="status">
            {message.text}
          </span>
        )}
      </div>
    </div>
  );
}
