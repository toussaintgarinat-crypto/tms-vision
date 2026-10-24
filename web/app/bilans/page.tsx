"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { DragEvent, FormEvent, useEffect, useState } from "react";

import { formatHours } from "./recurrenceFormat";
import { BilanFolder, StoredBilan } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Zone de dépôt « sans dossier » (les dossiers utilisent leur identifiant).
const NO_FOLDER = "none";

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // corps non JSON : message générique.
  }
  return `Erreur ${response.status}`;
}

export default function BilansPage() {
  const router = useRouter();
  const [bilans, setBilans] = useState<StoredBilan[] | null>(null);
  const [archives, setArchives] = useState<StoredBilan[] | null>(null);
  const [folders, setFolders] = useState<BilanFolder[]>([]);
  const [showArchives, setShowArchives] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [newFolderName, setNewFolderName] = useState("");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDeleteFolderId, setConfirmDeleteFolderId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [workdayHours, setWorkdayHours] = useState("9");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = <T,>(path: string) =>
      fetch(`${API_URL}${path}`).then((response) => {
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<T>;
      });
    Promise.all([
      load<StoredBilan[]>("/bilans?archived=false"),
      load<StoredBilan[]>("/bilans?archived=true"),
      load<BilanFolder[]>("/bilan-folders"),
    ])
      .then(([active, archived, folderList]) => {
        if (!cancelled) {
          setBilans(active);
          setArchives(archived);
          setFolders(folderList);
          setError(null);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBilans(null);
          setArchives(null);
          setError("Impossible de charger les bilans (problème réseau ou serveur).");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [reloadToken]);

  // Envoie une requête d'action, puis recharge les listes. Un message d'erreur lisible sinon.
  async function run(request: () => Promise<Response>, busy: string | null = null): Promise<boolean> {
    setBusyId(busy);
    setActionError(null);
    try {
      const response = await request();
      if (!response.ok) {
        setActionError(await errorMessage(response));
        return false;
      }
      setReloadToken((token) => token + 1);
      return true;
    } catch {
      setActionError("L'action a échoué (problème réseau ou serveur). Réessayez.");
      return false;
    } finally {
      setBusyId(null);
    }
  }

  const post = (path: string, body?: unknown) =>
    fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });

  function moveBilan(bilanId: string, target: string) {
    return run(() => post(`/bilans/${encodeURIComponent(bilanId)}/folder`, {
      folder_id: target === NO_FOLDER ? null : target,
    }), bilanId);
  }

  async function handleAction(bilan: StoredBilan, action: "archive" | "unarchive" | "delete") {
    const url = `/bilans/${encodeURIComponent(bilan.id)}`;
    const done = await run(
      () => (action === "delete"
        ? fetch(`${API_URL}${url}`, { method: "DELETE" })
        : post(`${url}/${action}`)),
      bilan.id,
    );
    if (done) setConfirmDeleteId(null);
  }

  async function handleCreateFolder(event: FormEvent) {
    event.preventDefault();
    const name = newFolderName.trim();
    if (!name) return;
    if (await run(() => post("/bilan-folders", { name }))) setNewFolderName("");
  }

  async function handleRenameFolder(event: FormEvent, folder: BilanFolder) {
    event.preventDefault();
    const done = await run(() => fetch(`${API_URL}/bilan-folders/${encodeURIComponent(folder.id)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: renameValue.trim() }),
    }), folder.id);
    if (done) setRenamingId(null);
  }

  async function handleDeleteFolder(folder: BilanFolder) {
    const done = await run(() => fetch(`${API_URL}/bilan-folders/${encodeURIComponent(folder.id)}`, {
      method: "DELETE",
    }), folder.id);
    if (done) setConfirmDeleteFolderId(null);
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    const hours = Number(workdayHours);
    if (!Number.isFinite(hours) || hours <= 0 || hours > 24) {
      setSubmitError("La durée de journée doit être comprise entre 0 et 24 heures.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const response = await post("/bilans", { label: label.trim() || null, workday_hours: hours });
      if (!response.ok) throw new Error(`Erreur ${response.status}`);
      const created = (await response.json()) as StoredBilan;
      router.push(`/bilans/${encodeURIComponent(created.id)}`);
    } catch {
      setSubmitError("Impossible de créer le bilan (problème réseau ou serveur).");
      setSubmitting(false);
    }
  }

  // Glisser-déposer : la ligne porte l'identifiant du bilan, le dossier ou « sans dossier » le reçoit.
  function onDragStart(event: DragEvent, bilan: StoredBilan) {
    event.dataTransfer.setData("text/plain", bilan.id);
    event.dataTransfer.effectAllowed = "move";
  }
  function dropProps(target: string) {
    return {
      onDragOver: (event: DragEvent) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = "move";
        if (dropTarget !== target) setDropTarget(target);
      },
      onDragLeave: (event: DragEvent) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDropTarget(null);
      },
      onDrop: (event: DragEvent) => {
        event.preventDefault();
        setDropTarget(null);
        const bilanId = event.dataTransfer.getData("text/plain");
        if (bilanId) void moveBilan(bilanId, target);
      },
    };
  }

  function renderRow(bilan: StoredBilan) {
    return (
      <li
        key={bilan.id}
        draggable
        onDragStart={(event) => onDragStart(event, bilan)}
        onDragEnd={() => setDropTarget(null)}
        className="flex cursor-grab flex-wrap items-center justify-between gap-2 rounded border bg-background p-3 text-sm active:cursor-grabbing"
      >
        <span>
          <span aria-hidden="true" className="mr-2 text-zinc-400">⠿</span>
          {bilan.label ?? "Sans libellé"} · {formatHours(bilan.workday_hours)} ·{" "}
          {new Date(bilan.created_at).toLocaleString("fr-FR")}
          {bilan.archived_at && (
            <span className="text-gray-500">
              {" "}· archivé le {new Date(bilan.archived_at).toLocaleDateString("fr-FR")}
            </span>
          )}
        </span>
        <span className="flex flex-wrap items-center gap-3">
          <select
            aria-label={`Déplacer « ${bilan.label ?? "Sans libellé"} » vers un dossier`}
            value={bilan.folder_id && folders.some((f) => f.id === bilan.folder_id) ? bilan.folder_id : NO_FOLDER}
            disabled={busyId === bilan.id}
            onChange={(event) => void moveBilan(bilan.id, event.target.value)}
            className="max-w-[10rem] rounded border p-1 text-xs"
          >
            <option value={NO_FOLDER}>Sans dossier</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>{folder.name}</option>
            ))}
          </select>
          <a href={`/bilans/${encodeURIComponent(bilan.id)}`} className="text-blue-600 underline">
            Ouvrir
          </a>
          <button
            type="button"
            disabled={busyId === bilan.id}
            onClick={() => handleAction(bilan, showArchives ? "unarchive" : "archive")}
            className="text-blue-600 underline disabled:opacity-50"
          >
            {showArchives ? "Restaurer" : "Archiver"}
          </button>
          {confirmDeleteId === bilan.id ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                disabled={busyId === bilan.id}
                onClick={() => handleAction(bilan, "delete")}
                className="rounded border border-red-600 px-2 py-0.5 text-red-600 disabled:opacity-50"
              >
                Supprimer définitivement
              </button>
              <button type="button" onClick={() => setConfirmDeleteId(null)} className="underline">
                Annuler
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirmDeleteId(bilan.id)} className="text-red-600 underline">
              Supprimer
            </button>
          )}
        </span>
      </li>
    );
  }

  const current = (showArchives ? archives : bilans) ?? [];
  const knownFolderIds = new Set(folders.map((folder) => folder.id));
  const inFolder = (folderId: string) => current.filter((bilan) => bilan.folder_id === folderId);
  const withoutFolder = current.filter((bilan) => !bilan.folder_id || !knownFolderIds.has(bilan.folder_id));
  const zoneClass = (target: string) =>
    `rounded border p-3 transition-colors ${dropTarget === target ? "border-blue-600 bg-blue-50 dark:bg-blue-950" : ""}`;

  function renderFolder(folder: BilanFolder) {
    const items = inFolder(folder.id);
    return (
      <details key={folder.id} open className={zoneClass(folder.id)} {...dropProps(folder.id)}>
        <summary className="cursor-pointer font-semibold">
          <span aria-hidden="true">📁 </span>
          {folder.name} <span className="font-normal text-gray-500">({items.length})</span>
        </summary>
        <div className="mt-2 flex flex-wrap items-center gap-3 text-sm">
          {renamingId === folder.id ? (
            <form onSubmit={(event) => handleRenameFolder(event, folder)} className="flex items-center gap-2">
              <input
                autoFocus
                value={renameValue}
                onChange={(event) => setRenameValue(event.target.value)}
                aria-label="Nouveau nom du dossier"
                maxLength={80}
                className="rounded border p-1"
              />
              <button type="submit" className="text-blue-600 underline">Enregistrer</button>
              <button type="button" onClick={() => setRenamingId(null)} className="underline">
                Annuler
              </button>
            </form>
          ) : (
            <button
              type="button"
              onClick={() => { setRenamingId(folder.id); setRenameValue(folder.name); }}
              className="text-blue-600 underline"
            >
              Renommer le dossier
            </button>
          )}
          {confirmDeleteFolderId === folder.id ? (
            <span className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => handleDeleteFolder(folder)}
                className="rounded border border-red-600 px-2 py-0.5 text-red-600"
              >
                Supprimer le dossier
              </button>
              <button type="button" onClick={() => setConfirmDeleteFolderId(null)} className="underline">
                Annuler
              </button>
            </span>
          ) : (
            <button type="button" onClick={() => setConfirmDeleteFolderId(folder.id)} className="text-red-600 underline">
              Supprimer le dossier
            </button>
          )}
        </div>
        {confirmDeleteFolderId === folder.id && (
          <p className="mt-2 text-sm text-gray-600">
            Les bilans de ce dossier ne sont pas supprimés : ils repassent « sans dossier ».
          </p>
        )}
        <ul className="mt-3 flex flex-col gap-2">
          {items.map(renderRow)}
          {items.length === 0 && (
            <li className="rounded border border-dashed p-3 text-sm text-gray-500">
              Dossier vide : glissez un bilan ici.
            </li>
          )}
        </ul>
      </details>
    );
  }

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Bilans de poste</h1>
        <Link href="/" className="text-sm text-blue-600 underline">
          ← Nouvelle analyse
        </Link>
      </div>

      <form onSubmit={handleCreate} className="grid gap-4 rounded border p-4 sm:grid-cols-3">
        <label className="flex flex-col gap-1 text-sm sm:col-span-2">
          Libellé du poste
          <input
            type="text"
            value={label}
            onChange={(event) => setLabel(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Journée de travail (heures)
          <input
            type="number"
            min="0.5"
            max="24"
            step="0.5"
            value={workdayHours}
            onChange={(event) => setWorkdayHours(event.target.value)}
            className="rounded border p-2"
          />
        </label>
        <div className="sm:col-span-3">
          <button
            type="submit"
            disabled={submitting}
            className="rounded border border-black px-3 py-1 text-sm disabled:opacity-50"
          >
            Créer un bilan
          </button>
          {submitError && <p className="mt-2 text-red-600">{submitError}</p>}
        </div>
      </form>

      {error && <p className="text-red-600">{error}</p>}
      {bilans === null && !error && <p>Chargement...</p>}
      {bilans !== null && archives !== null && (
        <>
          <div className="flex gap-2 border-b" role="tablist" aria-label="Bilans">
            <button
              type="button"
              role="tab"
              aria-selected={!showArchives}
              onClick={() => setShowArchives(false)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${!showArchives ? "border-black font-semibold" : "border-transparent text-gray-600"}`}
            >
              Bilans ({bilans.length})
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={showArchives}
              onClick={() => setShowArchives(true)}
              className={`-mb-px border-b-2 px-3 py-2 text-sm ${showArchives ? "border-black font-semibold" : "border-transparent text-gray-600"}`}
            >
              Archives ({archives.length})
            </button>
          </div>

          <form onSubmit={handleCreateFolder} className="flex flex-wrap items-end gap-3">
            <label className="flex min-w-[14rem] flex-1 flex-col gap-1 text-sm">
              Nouveau dossier (par exemple une entreprise)
              <input
                value={newFolderName}
                onChange={(event) => setNewFolderName(event.target.value)}
                maxLength={80}
                placeholder="Ex. Acme Industrie"
                className="rounded border p-2"
              />
            </label>
            <button type="submit" className="rounded border border-black px-3 py-2 text-sm">
              Créer le dossier
            </button>
          </form>
          <p className="-mt-3 text-xs text-gray-500">
            Glissez un bilan sur un dossier pour l&apos;y ranger, ou choisissez le dossier dans la liste de
            sa ligne. Les dossiers sont communs aux bilans et aux archives.
          </p>

          {actionError && <p className="text-red-600">{actionError}</p>}

          <div className="flex flex-col gap-3">
            {folders.map(renderFolder)}
            <section className={zoneClass(NO_FOLDER)} {...dropProps(NO_FOLDER)}>
              {folders.length > 0 && (
                <h2 className="mb-3 font-semibold">
                  Sans dossier <span className="font-normal text-gray-500">({withoutFolder.length})</span>
                </h2>
              )}
              <ul className="flex flex-col gap-2">
                {withoutFolder.map(renderRow)}
                {withoutFolder.length === 0 && (
                  <li className="text-sm text-gray-600">
                    {showArchives
                      ? "Aucun bilan archivé hors dossier. Archivez un bilan pour le ranger sans le perdre."
                      : folders.length > 0 ? "Aucun bilan hors dossier." : "Aucun bilan enregistré."}
                  </li>
                )}
              </ul>
            </section>
          </div>
        </>
      )}
    </main>
  );
}
