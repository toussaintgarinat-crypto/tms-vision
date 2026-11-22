"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n/I18nProvider";
import { ValidationBadge, ValidationLabel } from "../ValidationBadge";
import { ImportItem, readBundle, saveBlob, summarize } from "./exchange";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type MySheet = {
  id: string;
  title: string;
  zone: string;
  validation: ValidationLabel & { archived: boolean; imported?: boolean; copied_from: { id: string; title: string } | null };
};
type CatalogEntry = { id: string; title: string; zone: string };

// « Mes fiches » : les fiches créées ou copiées par l'ostéopathe connecté, la copie d'une fiche
// existante (de fichier ou d'un confrère) et la création d'une nouvelle fiche.
export default function MySheetsPage() {
  const { t } = useI18n();
  const { user } = useAuth();
  const router = useRouter();
  const [sheets, setSheets] = useState<MySheet[] | null>(null);
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [source, setSource] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showArchived, setShowArchived] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [importReport, setImportReport] = useState<ImportItem[] | null>(null);
  const [busy, setBusy] = useState(false);
  const isOsteopath = user?.roles.includes("osteopathe") ?? false;

  const load = useCallback(async () => {
    try {
      const [mine, all] = await Promise.all([fetch(`${API_URL}/sheets/mine`), fetch(`${API_URL}/exercises`)]);
      if (!mine.ok || !all.ok) throw new Error("load");
      setSheets((await mine.json()) as MySheet[]);
      setCatalog((await all.json()) as CatalogEntry[]);
    } catch {
      setError(t("sheets.loadFailed"));
    }
  }, [t]);

  useEffect(() => {
    if (!isOsteopath) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
  }, [load, isOsteopath]);

  async function copy() {
    if (!source) return;
    setError(null);
    const response = await fetch(`${API_URL}/exercises/${encodeURIComponent(source)}/copy`, { method: "POST" });
    if (!response.ok) {
      setError(t("sheets.copyFailed"));
      return;
    }
    const created = (await response.json()) as { id: string };
    router.push(`/fiches/${encodeURIComponent(created.id)}`);
  }

  // Télécharge un fichier d'échange : les fiches cochées, toutes les miennes ou tout le catalogue.
  async function exportSheets(query: string) {
    setError(null);
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/sheets/export?${query}`);
      if (!response.ok) throw new Error(String(response.status));
      saveBlob(await response.blob(), `fiches-tms-vision-${new Date().toISOString().slice(0, 10)}.json`);
    } catch {
      setError(t("sheets.exchange.exportFailed"));
    } finally {
      setBusy(false);
    }
  }

  // Importe un fichier d'échange : le serveur revérifie chaque fiche et dit ce qu'il en a fait.
  async function importFile(file: File | undefined) {
    if (!file) return;
    setError(null);
    setImportReport(null);
    const read = readBundle(await file.text(), file.size);
    if (!read.ok) return setError(t(`sheets.exchange.read.${read.reason}`));
    setBusy(true);
    try {
      const response = await fetch(`${API_URL}/sheets/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(read.bundle),
      });
      const body = (await response.json().catch(() => null)) as { report?: ImportItem[]; detail?: string } | null;
      if (!response.ok || !body?.report) {
        return setError(typeof body?.detail === "string" ? body.detail : t("sheets.exchange.importFailed"));
      }
      setImportReport(body.report);
      await load();
    } catch {
      setError(t("sheets.exchange.importFailed"));
    } finally {
      setBusy(false);
    }
  }

  if (!user) return null;
  if (!isOsteopath) return <main className="mx-auto w-full max-w-3xl flex-1 p-6 text-sm">{t("queue.forbidden")}</main>;

  const visible = (sheets ?? []).filter((sheet) => showArchived || !sheet.validation.archived);
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-5 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{t("sheets.title")}</h1>
        <Link href="/fiches/nouvelle" className="rounded bg-blue-700 px-3 py-2 text-sm font-semibold text-white">
          {t("sheets.new")}
        </Link>
      </div>
      <p className="text-sm text-gray-700">{t("sheets.intro")}</p>

      <section className="flex flex-wrap items-center gap-2 rounded border p-3 text-sm">
        <label className="flex items-center gap-2">
          {t("sheets.copyLabel")}
          <select value={source} onChange={(event) => setSource(event.target.value)} className="max-w-xs rounded border p-1">
            <option value="">{t("program.choose")}</option>
            {catalog.map((entry) => (
              <option key={entry.id} value={entry.id}>
                {entry.title}
              </option>
            ))}
          </select>
        </label>
        <button type="button" disabled={!source} onClick={() => void copy()} className="rounded border border-blue-600 px-3 py-1 text-blue-800 disabled:opacity-50">
          {t("sheets.copy")}
        </button>
        <span className="w-full text-xs text-gray-600">{t("sheets.copyHelp")}</span>
      </section>

      <section className="flex flex-col gap-2 rounded border p-3 text-sm" aria-label={t("sheets.exchange.title")}>
        <h2 className="font-semibold">{t("sheets.exchange.title")}</h2>
        <p className="text-xs text-gray-600">{t("sheets.exchange.help")}</p>
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" disabled={busy || selected.length === 0} onClick={() => void exportSheets(`ids=${encodeURIComponent(selected.join(","))}`)} className="rounded border border-blue-600 px-3 py-1 text-blue-800 disabled:opacity-50">
            {t("sheets.exchange.exportSelection", { count: selected.length })}
          </button>
          <button type="button" disabled={busy} onClick={() => void exportSheets("scope=mine")} className="rounded border border-blue-600 px-3 py-1 text-blue-800 disabled:opacity-50">
            {t("sheets.exchange.exportMine")}
          </button>
          <button type="button" disabled={busy} onClick={() => void exportSheets("scope=all")} className="rounded border border-blue-600 px-3 py-1 text-blue-800 disabled:opacity-50">
            {t("sheets.exchange.exportAll")}
          </button>
        </div>
        <label className="flex flex-wrap items-center gap-2">
          {t("sheets.exchange.import")}
          <input type="file" accept="application/json,.json" disabled={busy} onChange={(event) => { void importFile(event.target.files?.[0]); event.target.value = ""; }} />
        </label>
        <p className="text-xs text-gray-600">{t("sheets.exchange.importHelp")}</p>
        {importReport && (
          <div role="status" className="rounded bg-gray-50 p-2 text-xs">
            <p className="font-semibold">
              {t("sheets.exchange.summary", summarize(importReport))}
            </p>
            <ul className="mt-1 list-disc pl-5">
              {importReport.filter((item) => item.status !== "imported").map((item, index) => (
                <li key={index}>
                  {item.title || t("sheets.untitled")} : {item.status === "duplicate" ? t("sheets.exchange.duplicate") : item.error}
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={showArchived} onChange={(event) => setShowArchived(event.target.checked)} />
        {t("sheets.showArchived")}
      </label>
      {sheets !== null && visible.length === 0 && <p className="text-sm text-gray-600">{t("sheets.none")}</p>}
      <ul className="flex flex-col gap-2">
        {visible.map((sheet) => (
          <li key={sheet.id} className="rounded border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(sheet.id)}
                  onChange={(event) =>
                    setSelected((previous) => (event.target.checked ? [...previous, sheet.id] : previous.filter((id) => id !== sheet.id)))
                  }
                  aria-label={t("sheets.exchange.select", { title: sheet.title })}
                />
              <Link href={`/fiches/${encodeURIComponent(sheet.id)}`} className="font-semibold text-blue-800 underline">
                {sheet.title}
              </Link>
              </label>
              {sheet.validation.archived && (
                <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs">{t("sheets.archived")}</span>
              )}
            </div>
            <p className="mt-1 text-xs">
              <ValidationBadge label={sheet.validation} />
            </p>
            {sheet.validation.imported && (
              <p className="mt-1 text-xs text-gray-600">{t("sheets.exchange.importedNote")}</p>
            )}
            {sheet.validation.copied_from && (
              <p className="mt-1 text-xs text-gray-600">
                {t("sheets.copiedFrom", { title: sheet.validation.copied_from.title })}
              </p>
            )}
          </li>
        ))}
      </ul>
    </main>
  );
}
