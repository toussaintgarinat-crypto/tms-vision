"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { API_URL, problemText, readProblem } from "../auth/authFetch";
import { useAuth } from "../auth/AuthProvider";
import { RecoveryCode } from "../auth/RecoveryCode";
import { useI18n } from "../i18n/I18nProvider";

type EmailSettings = {
  configured: boolean;
  cabinet_fallback: boolean;
  encryption_available: boolean;
  address?: string;
  host?: string;
  port?: number;
  security?: string;
  username?: string;
  password_set?: boolean;
  status?: "connected" | "untested";
};

const SECURITY = ["starttls", "ssl", "none"] as const;
const PORTS = [587, 465, 25, 2525];

function PasswordSection() {
  const { t } = useI18n();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    const response = await fetch(`${API_URL}/auth/password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ current, new: next }),
    }).catch(() => null);
    if (!response) return setMessage({ ok: false, text: t("auth.error.network") });
    if (!response.ok) {
      const problem = readProblem(await response.json().catch(() => null));
      return setMessage({ ok: false, text: problemText(problem, t, t("auth.error.generic")) });
    }
    setCurrent("");
    setNext("");
    setMessage({ ok: true, text: t("account.password.done") });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded border p-4">
      <h2 className="text-lg font-semibold">{t("account.password.title")}</h2>
      <label className="flex flex-col gap-1 text-sm">
        {t("account.password.current")}
        <input type="password" autoComplete="current-password" required value={current} onChange={(e) => setCurrent(e.target.value)} className="rounded border p-2" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("account.password.new")}
        <input type="password" autoComplete="new-password" required value={next} onChange={(e) => setNext(e.target.value)} className="rounded border p-2" />
        <span className="text-xs text-zinc-500">{t("account.password.rules")}</span>
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" className="rounded border border-black px-3 py-1 text-sm">{t("account.password.button")}</button>
        {message && <span role="status" className={`text-sm ${message.ok ? "text-green-700" : "text-red-700"}`}>{message.text}</span>}
      </div>
    </form>
  );
}

function LoginEmailSection() {
  const { t } = useI18n();
  const { user, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setMessage(null);
    const response = await fetch(`${API_URL}/auth/email`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    }).catch(() => null);
    if (!response) return setMessage({ ok: false, text: t("auth.error.network") });
    if (!response.ok) {
      const problem = readProblem(await response.json().catch(() => null));
      return setMessage({ ok: false, text: problemText(problem, t, t("auth.error.generic")) });
    }
    setEmail("");
    setPassword("");
    await refresh();
    setMessage({ ok: true, text: t("account.loginEmail.done") });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded border p-4">
      <h2 className="text-lg font-semibold">{t("account.loginEmail.title")}</h2>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{t("account.loginEmail.help", { email: user?.email ?? "" })}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t("account.loginEmail.new")}
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="rounded border p-2" />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("account.password.current")}
        <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="rounded border p-2" />
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" className="rounded border border-black px-3 py-1 text-sm">{t("account.loginEmail.button")}</button>
        {message && <span role="status" className={`text-sm ${message.ok ? "text-green-700" : "text-red-700"}`}>{message.text}</span>}
      </div>
    </form>
  );
}

// Application de bureau : nouveau code de récupération (« mot de passe oublié » sans email).
function RecoverySection() {
  const { t } = useI18n();
  const { status } = useAuth();
  const [password, setPassword] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  if (!status?.desktop) return null;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const response = await fetch(`${API_URL}/auth/recovery-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    }).catch(() => null);
    if (!response) return setError(t("auth.error.network"));
    if (!response.ok) return setError(problemText(readProblem(await response.json().catch(() => null)), t, t("auth.error.generic")));
    setPassword("");
    setCode(((await response.json()) as { recovery_code: string }).recovery_code);
  }

  if (code) return <RecoveryCode code={code} onDone={() => setCode(null)} />;
  return (
    <form onSubmit={submit} className="flex flex-col gap-3 rounded border p-4">
      <h2 className="text-lg font-semibold">{t("recovery.section")}</h2>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{t("recovery.sectionHelp")}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t("account.password.current")}
        <input type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} className="rounded border p-2" />
      </label>
      <div className="flex items-center gap-3">
        <button type="submit" className="rounded border border-black px-3 py-1 text-sm">{t("recovery.new")}</button>
        {error && <span role="alert" className="text-sm text-red-700">{error}</span>}
      </div>
    </form>
  );
}

function EmailSection() {
  const { t } = useI18n();
  const [settings, setSettings] = useState<EmailSettings | null>(null);
  const [form, setForm] = useState({ address: "", host: "", port: 587, security: "starttls", username: "", password: "" });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const apply = useCallback((data: EmailSettings) => {
    setSettings(data);
    if (data.configured) {
      setForm({
        address: data.address ?? "",
        host: data.host ?? "",
        port: data.port ?? 587,
        security: data.security ?? "starttls",
        username: data.username ?? "",
        password: "",
      });
    }
  }, []);

  useEffect(() => {
    fetch(`${API_URL}/me/email`)
      .then((response) => (response.ok ? (response.json() as Promise<EmailSettings>) : null))
      .then((data) => data && apply(data))
      .catch(() => setMessage({ ok: false, text: t("auth.error.network") }));
  }, [apply, t]);

  // Serveur et port se remplissent seuls pour les fournisseurs courants.
  async function suggest() {
    if (form.host || !form.address.includes("@")) return;
    const response = await fetch(`${API_URL}/me/email/suggest?address=${encodeURIComponent(form.address)}`).catch(() => null);
    const body = response?.ok ? ((await response.json()) as { suggestion: { host: string; port: number; security: string } | null }) : null;
    if (body?.suggestion) setForm((current) => ({ ...current, ...body.suggestion! }));
  }

  async function call(kind: "save" | "test" | "delete") {
    setBusy(kind);
    setMessage(null);
    try {
      const response = await fetch(`${API_URL}/me/email${kind === "test" ? "/test" : ""}`, {
        method: kind === "save" ? "PUT" : kind === "delete" ? "DELETE" : "POST",
        headers: { "Content-Type": "application/json" },
        body: kind === "save" ? JSON.stringify({ ...form, port: Number(form.port) }) : undefined,
      });
      if (!response.ok) {
        const problem = readProblem(await response.json().catch(() => null));
        return setMessage({ ok: false, text: problemText(problem, t, t("auth.error.generic")) });
      }
      apply((await response.json()) as EmailSettings);
      if (kind === "delete") setForm({ address: "", host: "", port: 587, security: "starttls", username: "", password: "" });
      setMessage({ ok: true, text: t(`account.email.done.${kind}`) });
    } catch {
      setMessage({ ok: false, text: t("auth.error.network") });
    } finally {
      setBusy(null);
    }
  }

  const field = (key: keyof typeof form) => ({
    value: form[key],
    onChange: (event: { target: { value: string } }) => setForm({ ...form, [key]: event.target.value }),
  });
  const statusKey = settings?.configured ? (settings.status === "connected" ? "connected" : "untested") : "none";

  return (
    <section className="flex flex-col gap-3 rounded border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">{t("account.email.title")}</h2>
        <span className={`rounded px-2 py-0.5 text-xs ${statusKey === "connected" ? "bg-green-100 text-green-900" : "bg-zinc-100 text-zinc-800"}`}>
          {t(`account.email.status.${statusKey}`)}
        </span>
      </div>
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{t("account.email.help")}</p>
      {settings && !settings.encryption_available && (
        <p className="rounded border border-amber-400 bg-amber-50 p-2 text-sm text-amber-900">{t("account.email.noKey")}</p>
      )}
      {settings && !settings.configured && (
        <p className="text-xs text-zinc-500">{t(settings.cabinet_fallback ? "account.email.fallback" : "account.email.noFallback")}</p>
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          {t("account.email.address")}
          <input type="email" {...field("address")} onBlur={() => void suggest()} className="rounded border p-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("account.email.host")}
          <input {...field("host")} placeholder="smtp.gmail.com" className="rounded border p-2" />
        </label>
        <div className="flex gap-3">
          <label className="flex flex-1 flex-col gap-1 text-sm">
            {t("account.email.port")}
            <select value={form.port} onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} className="rounded border p-2">
              {PORTS.map((port) => <option key={port} value={port}>{port}</option>)}
            </select>
          </label>
          <label className="flex flex-1 flex-col gap-1 text-sm">
            {t("account.email.security")}
            <select {...field("security")} className="rounded border p-2">
              {SECURITY.map((mode) => <option key={mode} value={mode}>{t(`account.email.security.${mode}`)}</option>)}
            </select>
          </label>
        </div>
        <label className="flex flex-col gap-1 text-sm">
          {t("account.email.username")}
          <input {...field("username")} placeholder={form.address} className="rounded border p-2" />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("account.email.password")}
          <input type="password" autoComplete="new-password" {...field("password")} placeholder={settings?.password_set ? "••••••••" : ""} className="rounded border p-2" />
          <span className="text-xs text-zinc-500">{t(settings?.password_set ? "account.email.passwordKeep" : "account.email.passwordHelp")}</span>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button type="button" disabled={busy !== null} onClick={() => void call("save")} className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50">{t("common.save")}</button>
        <button type="button" disabled={busy !== null || !settings?.configured} onClick={() => void call("test")} className="rounded border px-3 py-1 text-sm disabled:opacity-50">
          {busy === "test" ? t("account.email.testing") : t("account.email.test")}
        </button>
        <button type="button" disabled={busy !== null || !settings?.configured} onClick={() => void call("delete")} className="rounded border border-red-600 px-3 py-1 text-sm text-red-600 disabled:opacity-50">{t("account.email.remove")}</button>
        {message && <span role="status" className={`text-sm ${message.ok ? "text-green-700" : "text-red-700"}`}>{message.text}</span>}
      </div>
    </section>
  );
}

export default function AccountPage() {
  const { t } = useI18n();
  const { user, logout } = useAuth();
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-semibold">{t("account.title")}</h1>
          {user && (
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              {user.name} · {user.email} · {user.roles.map((role) => t(`auth.role.${role}`)).join(", ")}
            </p>
          )}
        </div>
        <button type="button" onClick={() => void logout()} className="rounded border px-3 py-1 text-sm">{t("auth.logout")}</button>
      </div>
      <EmailSection />
      <LoginEmailSection />
      <PasswordSection />
      <RecoverySection />
    </main>
  );
}
