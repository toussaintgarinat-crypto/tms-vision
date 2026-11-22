"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "../auth/AuthProvider";
import { useI18n } from "../i18n/I18nProvider";
import { ValidationBadge, ValidationLabel } from "../ValidationBadge";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type MySheet = {
  id: string;
  title: string;
  zone: string;
  validation: ValidationLabel & { archived: boolean; copied_from: { id: string; title: string } | null };
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
              <Link href={`/fiches/${encodeURIComponent(sheet.id)}`} className="font-semibold text-blue-800 underline">
                {sheet.title}
              </Link>
              {sheet.validation.archived && (
                <span className="rounded bg-gray-200 px-1.5 py-0.5 text-xs">{t("sheets.archived")}</span>
              )}
            </div>
            <p className="mt-1 text-xs">
              <ValidationBadge label={sheet.validation} />
            </p>
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
