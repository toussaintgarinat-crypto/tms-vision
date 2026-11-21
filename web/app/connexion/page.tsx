"use client";

import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { API_URL, problemText, readProblem } from "../auth/authFetch";
import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n/I18nProvider";

export default function LoginPage() {
  const { t } = useI18n();
  const router = useRouter();
  const { status, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        const problem = readProblem(await response.json().catch(() => null));
        setError(problemText(problem, t, t("auth.error.generic")));
        return;
      }
      setPassword("");
      await refresh();
      router.replace("/");
    } catch {
      setError(t("auth.error.network"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col justify-center gap-4 p-6">
      <h1 className="text-2xl font-semibold">{t("auth.login.title")}</h1>
      {status?.setup_required && (
        <p className="rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
          {t("auth.login.setupRequired")}
        </p>
      )}
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          {t("auth.email")}
          <input
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          {t("auth.password")}
          <input
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="rounded border border-black bg-blue-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          {busy ? t("auth.login.busy") : t("auth.login.button")}
        </button>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
      </form>
      <p className="text-xs text-zinc-500">{t("auth.login.forgot")}</p>
    </main>
  );
}
