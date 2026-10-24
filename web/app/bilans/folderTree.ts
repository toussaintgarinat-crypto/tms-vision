import { BilanFolder } from "./types";

export const PATH_SEPARATOR = " › ";

function byName(a: BilanFolder, b: BilanFolder): number {
  return a.name.localeCompare(b.name, "fr", { sensitivity: "base" });
}

// Un dossier dont le parent n'existe plus compte comme un dossier de la racine.
function parentOf(folder: BilanFolder, ids: Set<string>): string | null {
  return folder.parent_id && ids.has(folder.parent_id) ? folder.parent_id : null;
}

/** Sous-dossiers directs d'un dossier (`null` : la racine), par ordre alphabétique. */
export function childrenOf(folders: BilanFolder[], parentId: string | null): BilanFolder[] {
  const ids = new Set(folders.map((folder) => folder.id));
  return folders.filter((folder) => parentOf(folder, ids) === parentId).sort(byName);
}

/** Identifiants de tous les dossiers situés sous `folderId` (sans lui-même). */
export function descendantIds(folders: BilanFolder[], folderId: string): Set<string> {
  const found = new Set<string>();
  const visit = (id: string) => {
    for (const child of childrenOf(folders, id)) {
      if (!found.has(child.id)) {
        found.add(child.id);
        visit(child.id);
      }
    }
  };
  visit(folderId);
  return found;
}

/** Chemin lisible d'un dossier : « Acme › Production › Soudure ». */
export function folderPath(folders: BilanFolder[], folderId: string): string {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const names: string[] = [];
  const seen = new Set<string>();
  let current = byId.get(folderId);
  while (current && !seen.has(current.id)) {
    seen.add(current.id);
    names.unshift(current.name);
    current = current.parent_id ? byId.get(current.parent_id) : undefined;
  }
  return names.join(PATH_SEPARATOR);
}

/** Dossiers dans l'ordre de l'arbre (parent avant enfants), avec leur chemin, pour une liste de
 * choix. `excludeId` écarte un dossier et tout ce qu'il contient (destination interdite). */
export function folderOptions(
  folders: BilanFolder[],
  excludeId?: string,
): { id: string; label: string }[] {
  const options: { id: string; label: string }[] = [];
  const visit = (parentId: string | null) => {
    for (const folder of childrenOf(folders, parentId)) {
      if (folder.id === excludeId) continue;
      options.push({ id: folder.id, label: folderPath(folders, folder.id) });
      visit(folder.id);
    }
  };
  visit(null);
  return options;
}

/** Nombre de bilans dans un dossier et dans tous ses sous-dossiers. */
export function totalCount(
  folders: BilanFolder[],
  folderId: string,
  bilanCountByFolder: Map<string, number>,
): number {
  let total = bilanCountByFolder.get(folderId) ?? 0;
  for (const id of descendantIds(folders, folderId)) total += bilanCountByFolder.get(id) ?? 0;
  return total;
}
