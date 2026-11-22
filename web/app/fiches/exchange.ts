// Échange de fiches entre installations : lecture d'un fichier choisi par l'ostéopathe et compte
// rendu d'import. Le serveur revérifie tout ; ici on évite seulement d'envoyer un fichier qui n'en
// est manifestement pas un.

export const EXCHANGE_FORMAT = "tms-vision-fiches";
export const MAX_FILE_BYTES = 20 * 1024 * 1024;

export type ImportItem = { title: string; status: "imported" | "duplicate" | "invalid"; id?: string; error?: string };

export type ReadResult =
  | { ok: true; bundle: { format: string; version: number; sheets: unknown[] }; count: number }
  | { ok: false; reason: "tooBig" | "notJson" | "notBundle" | "empty" };

export function readBundle(text: string, size: number = text.length): ReadResult {
  if (size > MAX_FILE_BYTES) return { ok: false, reason: "tooBig" };
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    return { ok: false, reason: "notJson" };
  }
  const bundle = data as { format?: unknown; version?: unknown; sheets?: unknown } | null;
  if (!bundle || bundle.format !== EXCHANGE_FORMAT || typeof bundle.version !== "number" || !Array.isArray(bundle.sheets)) {
    return { ok: false, reason: "notBundle" };
  }
  if (bundle.sheets.length === 0) return { ok: false, reason: "empty" };
  return { ok: true, bundle: bundle as { format: string; version: number; sheets: unknown[] }, count: bundle.sheets.length };
}

// Nombre de fiches par statut dans un compte rendu d'import.
export function summarize(report: ImportItem[]): Record<ImportItem["status"], number> {
  const totals = { imported: 0, duplicate: 0, invalid: 0 };
  for (const item of report) totals[item.status] += 1;
  return totals;
}

// Fait télécharger `blob` par le navigateur sous `filename`.
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
