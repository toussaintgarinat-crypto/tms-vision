"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { API_URL, AuthUser, problemText, readProblem } from "../auth/authFetch";
import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n/I18nProvider";

const ROLES = ["praticien", "osteopathe", "administrateur"] as const;
type AuditEntry = { at: string; email: string | null; action: string; target: string | null; detail: string | null; address: string | null };

export default function AdministrationPage() {
  const { t, tag } = useI18n();
  const { user } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [resetting, setResetting] = useState<{ id: string; password: string } | null>(null);
  const [editing, setEditing] = useState<{ id: string; email: string } | null>(null);
  const [invite, setInvite] = useState({ email: "", name: "", message: "", osteopath: false });
  const [inviteState, setInviteState] = useState<"idle" | "busy" | "sent" | "not_configured" | "failed">("idle");
  const [form, setForm] = useState({ email: "", name: "", password: "", roles: ["praticien"] as string[] });

  const fetchAll = useCallback(async () => {
    const [usersResponse, auditResponse] = await Promise.all([
      fetch(`${API_URL}/admin/users`),
      fetch(`${API_URL}/admin/audit?limit=100`),
    ]).catch(() => [null, null] as const);
    if (!usersResponse?.ok || !auditResponse?.ok) {
      return {
        error: usersResponse?.status === 403 ? t("admin.forbidden") : t("auth.error.network"),
        users: [] as AuthUser[],
        audit: [] as AuditEntry[],
      };
    }
    return {
      error: null,
      users: (await usersResponse.json()) as AuthUser[],
      audit: (await auditResponse.json()) as AuditEntry[],
    };
  }, [t]);

  const show = useCallback((result: Awaited<ReturnType<typeof fetchAll>>) => {
    setError(result.error);
    if (!result.error) {
      setUsers(result.users);
      setAudit(result.audit);
    }
  }, []);

  const load = useCallback(() => fetchAll().then(show), [fetchAll, show]);

  useEffect(() => {
    let cancelled = false;
    void fetchAll().then((result) => {
      if (!cancelled) show(result);
    });
    return () => {
      cancelled = true;
    };
  }, [fetchAll, show]);

  async function send(path: string, method: string, body: unknown) {
    const response = await fetch(`${API_URL}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).catch(() => null);
    if (!response) return setError(t("auth.error.network"));
    if (!response.ok) return setError(problemText(readProblem(await response.json().catch(() => null)), t, t("auth.error.generic")));
    setError(null);
    await load();
    return true;
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    if (await send("/admin/users", "POST", form)) setForm({ email: "", name: "", password: "", roles: ["praticien"] });
  }

  const toggleRole = (current: string[], role: string) =>
    current.includes(role) ? current.filter((value) => value !== role) : [...current, role];

  async function sendInvitation(event: FormEvent) {
    event.preventDefault();
    setInviteState("busy");
    try {
      const response = await fetch(`${API_URL}/admin/invitations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...invite, name: invite.name || null, message: invite.message || null }),
      });
      if (!response.ok) return setInviteState("failed");
      const body = (await response.json()) as { email_status: "sent" | "not_configured" | "failed" };
      setInviteState(body.email_status);
      if (body.email_status === "sent") setInvite({ email: "", name: "", message: "", osteopath: false });
      void load();
    } catch {
      setInviteState("failed");
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-6 p-6">
      <h1 className="text-2xl font-semibold">{t("admin.title")}</h1>
      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{t("admin.users")}</h2>
        <ul className="flex flex-col gap-2">
          {users.map((account) => (
            <li key={account.id} className="flex flex-wrap items-center justify-between gap-3 rounded border p-3 text-sm">
              <span>
                <strong>{account.name}</strong> · {account.email}
                {!account.active && <span className="ml-2 rounded bg-zinc-200 px-2 py-0.5 text-xs text-zinc-800">{t("admin.inactive")}</span>}
              </span>
              <span className="flex flex-wrap items-center gap-3">
                {ROLES.map((role) => (
                  <label key={role} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={account.roles.includes(role)}
                      onChange={() => void send(`/admin/users/${account.id}`, "PATCH", { roles: toggleRole(account.roles, role) })}
                    />
                    {t(`auth.role.${role}`)}
                  </label>
                ))}
                <button
                  type="button"
                  onClick={() => setEditing({ id: account.id, email: account.email })}
                  className="rounded border px-2 py-0.5"
                >
                  {t("admin.changeEmail")}
                </button>
                <button
                  type="button"
                  onClick={() => setResetting({ id: account.id, password: "" })}
                  className="rounded border px-2 py-0.5"
                >
                  {t("admin.resetPassword")}
                </button>
                <button
                  type="button"
                  disabled={account.id === user?.id}
                  onClick={() => void send(`/admin/users/${account.id}`, "PATCH", { active: !account.active })}
                  className="rounded border px-2 py-0.5 disabled:opacity-40"
                >
                  {account.active ? t("admin.deactivate") : t("admin.activate")}
                </button>
              </span>
            </li>
          ))}
        </ul>
        {resetting && (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (await send(`/admin/users/${resetting.id}/password`, "POST", { password: resetting.password })) setResetting(null);
            }}
            className="flex flex-col gap-2 rounded border p-3 text-sm"
          >
            <label className="flex flex-col gap-1">
              {t("admin.newPasswordFor", { name: users.find((account) => account.id === resetting.id)?.name ?? "" })}
              <input type="password" autoComplete="new-password" required value={resetting.password} onChange={(e) => setResetting({ ...resetting, password: e.target.value })} className="rounded border p-2" />
            </label>
            <p className="text-xs text-zinc-500">{t("admin.resetNote")}</p>
            <div className="flex gap-3">
              <button type="submit" className="rounded border border-black px-3 py-1">{t("common.save")}</button>
              <button type="button" onClick={() => setResetting(null)} className="underline">{t("common.cancel")}</button>
            </div>
          </form>
        )}
        {editing && (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              if (await send(`/admin/users/${editing.id}`, "PATCH", { email: editing.email })) setEditing(null);
            }}
            className="flex flex-col gap-2 rounded border p-3 text-sm"
          >
            <label className="flex flex-col gap-1">
              {t("admin.newEmail", { name: users.find((account) => account.id === editing.id)?.name ?? "" })}
              <input type="email" required value={editing.email} onChange={(e) => setEditing({ ...editing, email: e.target.value })} className="rounded border p-2" />
            </label>
            <p className="text-xs text-zinc-500">{t("admin.changeEmailNote")}</p>
            <div className="flex gap-3">
              <button type="submit" className="rounded border border-black px-3 py-1">{t("common.save")}</button>
              <button type="button" onClick={() => setEditing(null)} className="underline">{t("common.cancel")}</button>
            </div>
          </form>
        )}
      </section>
      <form onSubmit={sendInvitation} className="grid gap-3 rounded border p-4 sm:grid-cols-2">
        <h2 className="text-lg font-semibold sm:col-span-2">{t("admin.invite.title")}</h2>
        <p className="text-sm text-zinc-600 sm:col-span-2">{t("admin.invite.help")}</p>
        <label className="flex flex-col gap-1 text-sm">{t("auth.email")}<input type="email" required value={invite.email} onChange={(e) => setInvite({ ...invite, email: e.target.value })} className="rounded border p-2" /></label>
        <label className="flex flex-col gap-1 text-sm">{t("admin.invite.name")}<input value={invite.name} onChange={(e) => setInvite({ ...invite, name: e.target.value })} className="rounded border p-2" /></label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">{t("admin.invite.message")}<textarea rows={2} value={invite.message} onChange={(e) => setInvite({ ...invite, message: e.target.value })} className="rounded border p-2" /></label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={invite.osteopath} onChange={(e) => setInvite({ ...invite, osteopath: e.target.checked })} />
          {t("admin.invite.osteopath")}
        </label>
        <div className="flex flex-wrap items-center gap-3 sm:col-span-2">
          <button type="submit" disabled={inviteState === "busy"} className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50">{t("admin.invite.send")}</button>
          {inviteState === "sent" && <span role="status" className="text-sm text-emerald-800">{t("admin.invite.sent")}</span>}
          {inviteState === "not_configured" && <span role="status" className="text-sm text-amber-800">{t("admin.invite.notConfigured")}</span>}
          {inviteState === "failed" && <span role="alert" className="text-sm text-red-700">{t("admin.invite.failed")}</span>}
        </div>
      </form>
      <form onSubmit={create} className="grid gap-3 rounded border p-4 sm:grid-cols-2">
        <h2 className="text-lg font-semibold sm:col-span-2">{t("admin.create")}</h2>
        <label className="flex flex-col gap-1 text-sm">{t("auth.email")}<input type="email" required value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} className="rounded border p-2" /></label>
        <label className="flex flex-col gap-1 text-sm">{t("admin.name")}<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded border p-2" /></label>
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">{t("admin.temporaryPassword")}<input type="password" autoComplete="new-password" required value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} className="rounded border p-2" /><span className="text-xs text-zinc-500">{t("account.password.rules")}</span></label>
        <fieldset className="flex flex-wrap gap-4 text-sm sm:col-span-2">
          {ROLES.map((role) => (
            <label key={role} className="flex items-center gap-1">
              <input type="checkbox" checked={form.roles.includes(role)} onChange={() => setForm({ ...form, roles: toggleRole(form.roles, role) })} />
              {t(`auth.role.${role}`)}
            </label>
          ))}
        </fieldset>
        <div className="sm:col-span-2"><button type="submit" disabled={form.roles.length === 0} className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50">{t("admin.createButton")}</button></div>
      </form>
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{t("admin.audit")}</h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-xs">
            <thead><tr className="border-b text-left"><th className="p-1">{t("admin.audit.when")}</th><th className="p-1">{t("admin.audit.who")}</th><th className="p-1">{t("admin.audit.action")}</th><th className="p-1">{t("admin.audit.detail")}</th></tr></thead>
            <tbody>
              {audit.map((entry, index) => (
                <tr key={index} className="border-b">
                  <td className="p-1 whitespace-nowrap">{new Date(entry.at).toLocaleString(tag)}</td>
                  <td className="p-1">{entry.email ?? "—"}</td>
                  <td className="p-1">{entry.action}</td>
                  <td className="p-1">{[entry.detail, entry.address].filter(Boolean).join(" · ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
