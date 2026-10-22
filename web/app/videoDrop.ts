const VIDEO_EXTENSIONS = [".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"];

function looksLikeVideo(file: { name: string; type: string }): boolean {
  if (file.type.startsWith("video/")) return true;
  // Certains navigateurs ne donnent pas de type pour .mov ou .mkv déposés.
  const name = file.name.toLowerCase();
  return file.type === "" && VIDEO_EXTENSIONS.some((extension) => name.endsWith(extension));
}

export type PickedVideo = { file: File; error: null } | { file: null; error: string };

/** Choisit la vidéo parmi des fichiers déposés ou sélectionnés : la première qui en est une. */
export function pickVideoFile(files: ArrayLike<File> | null | undefined): PickedVideo {
  const list = files ? Array.from(files) : [];
  if (list.length === 0) return { file: null, error: "Aucun fichier reçu." };
  const video = list.find(looksLikeVideo);
  if (!video) return { file: null, error: "Ce fichier n'est pas une vidéo." };
  if (video.size === 0) return { file: null, error: "Le fichier sélectionné est vide." };
  return { file: video, error: null };
}
