"use client";

import { useEffect, useState } from "react";

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
  enabled_locked: boolean;
  provider: string;
  base_url: string;
  model: string;
  key_set: boolean;
  transcription_url: string;
  transcription_key_set: boolean;
  providers: Provider[];
};

type Props = {
  /** Appelé après un enregistrement réussi (le bandeau relit la configuration du serveur). */
  onSaved: () => void;
};

async function detail(response: Response): Promise<string> {
  const body = (await response.json().catch(() => ({}))) as { detail?: string };
  return body.detail ?? `Erreur ${response.status}`;
}

export function AssistantSettingsPanel({ onSaved }: Props) {
  const [server, setServer] = useState<ServerSettings | null>(null);
  const [provider, setProvider] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [transcriptionUrl, setTranscriptionUrl] = useState("");
  const [transcriptionKey, setTranscriptionKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

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
      .catch(() => setMessage({ ok: false, text: "Impossible de lire les réglages du serveur." }));
  }, []);

  if (server === null) {
    return <p className="text-xs text-gray-600">{message?.text ?? "Chargement des réglages…"}</p>;
  }

  const current = server.providers.find((p) => p.id === provider);

  function chooseProvider(id: string) {
    setProvider(id);
    const next = server?.providers.find((p) => p.id === id);
    if (next && next.base_url) setBaseUrl(next.base_url);
    setModel("");
    setModels([]);
    setMessage(null);
  }

  /** Valeurs du formulaire ; une clé laissée vide n'est pas envoyée (= gardée). */
  function formValues() {
    return {
      provider,
      base_url: baseUrl,
      model,
      api_key: clearKey ? "" : apiKey !== "" ? apiKey : undefined,
      transcription_url: transcriptionUrl,
      transcription_key: transcriptionKey !== "" ? transcriptionKey : undefined,
    };
  }

  async function test() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/assistant/settings/test`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formValues()),
      });
      if (!response.ok) return setMessage({ ok: false, text: await detail(response) });
      const result = (await response.json()) as { ok: boolean; message: string; models: string[] };
      setModels(result.models);
      if (result.ok && model === "" && result.models.length > 0) setModel(result.models[0]);
      setMessage({ ok: result.ok, text: result.message });
    } catch {
      setMessage({ ok: false, text: "Impossible de joindre le serveur TMS Vision." });
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/assistant/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...formValues(), enabled: true }),
      });
      if (!response.ok) return setMessage({ ok: false, text: await detail(response) });
      setServer((await response.json()) as ServerSettings);
      setApiKey("");
      setClearKey(false);
      setTranscriptionKey("");
      setMessage({ ok: true, text: "Réglages enregistrés." });
      onSaved();
    } catch {
      setMessage({ ok: false, text: "Impossible d'enregistrer (problème réseau ou serveur)." });
    } finally {
      setBusy(false);
    }
  }

  const input = "rounded border p-2";

  return (
    <div className="flex flex-col gap-3 rounded border bg-gray-50 p-3 text-gray-900 dark:bg-transparent dark:text-inherit">
      <h4 className="font-semibold">Réglages de l&apos;assistant</h4>
      {server.enabled_locked && (
        <p className="text-xs text-amber-700">
          L&apos;administrateur a verrouillé l&apos;assistant (TMS_ASSISTANT dans le fichier .env) : il
          reste éteint tant que cette ligne n&apos;est pas retirée.
        </p>
      )}

      <label className="flex flex-col gap-1">
        Fournisseur d&apos;IA
        <select value={provider} onChange={(e) => chooseProvider(e.target.value)} className={input}>
          <option value="">— Choisir —</option>
          {server.providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        {current && <span className="text-xs text-gray-600">{current.hint}</span>}
      </label>

      <label className="flex flex-col gap-1">
        Adresse du serveur
        <input
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          placeholder="http://localhost:11434/v1"
          className={input}
        />
        {server.providers.some((p) => p.id === provider && p.local) && (
          <span className="text-xs text-gray-600">
            Sous Docker, « localhost » est converti automatiquement vers votre machine.
          </span>
        )}
      </label>

      {(current?.key_required || provider === "custom" || server.key_set) && (
        <label className="flex flex-col gap-1">
          Clé API
          <input
            type="password"
            autoComplete="off"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            disabled={clearKey}
            placeholder={server.key_set ? "Clé enregistrée (laisser vide pour la garder)" : "sk-…"}
            className={input}
          />
          {server.key_set && (
            <span className="flex items-center gap-1 text-xs">
              <input
                type="checkbox"
                checked={clearKey}
                onChange={(e) => setClearKey(e.target.checked)}
              />
              Effacer la clé enregistrée
            </span>
          )}
        </label>
      )}

      <label className="flex flex-col gap-1">
        Modèle
        <input
          value={model}
          onChange={(e) => setModel(e.target.value)}
          list="assistant-models"
          placeholder="Vide : le premier modèle du serveur"
          className={input}
        />
        <datalist id="assistant-models">
          {models.map((name) => (
            <option key={name} value={name} />
          ))}
        </datalist>
      </label>

      <details className="rounded border p-2">
        <summary className="cursor-pointer">Transcription souveraine (facultatif)</summary>
        <div className="mt-2 flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            Adresse du service de transcription
            <input
              value={transcriptionUrl}
              onChange={(e) => setTranscriptionUrl(e.target.value)}
              placeholder="http://localhost:5700"
              className={input}
            />
          </label>
          <label className="flex flex-col gap-1">
            Clé du service
            <input
              type="password"
              autoComplete="off"
              value={transcriptionKey}
              onChange={(e) => setTranscriptionKey(e.target.value)}
              placeholder={server.transcription_key_set ? "Clé enregistrée (laisser vide pour la garder)" : ""}
              className={input}
            />
          </label>
        </div>
      </details>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void test()}
          disabled={busy}
          className="rounded border px-3 py-1 disabled:opacity-50"
        >
          Tester la connexion
        </button>
        <button
          type="button"
          onClick={() => void save()}
          disabled={busy || provider === ""}
          className="rounded border border-black px-3 py-1 disabled:opacity-50"
        >
          Enregistrer
        </button>
        {message && (
          <span className={message.ok ? "text-green-700" : "text-red-600"} role="status">
            {message.text}
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500">
        La clé est conservée sur le serveur (dossier data/) et n&apos;est jamais renvoyée au navigateur.
      </p>
    </div>
  );
}
