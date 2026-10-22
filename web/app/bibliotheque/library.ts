import type { Exercise } from "../exercisePose";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Pathology = { id: string; label: string; exercises: string[] };
export type LibraryZone = { id: string; label: string; pathologies: Pathology[] };
export type Library = { status: "draft" | "validated"; note?: string; zones: LibraryZone[] };

// Identifiant de la « pathologie » qui regroupe tous les exercices d'une zone.
export const ALL_PATHOLOGIES = "all";

// Exercices à afficher pour une zone et une pathologie (ou toute la zone), sans doublon, dans
// l'ordre où la bibliothèque les cite.
export function exerciseIdsFor(zone: LibraryZone, pathologyId: string): string[] {
  const pathologies =
    pathologyId === ALL_PATHOLOGIES
      ? zone.pathologies
      : zone.pathologies.filter((pathology) => pathology.id === pathologyId);
  return [...new Set(pathologies.flatMap((pathology) => pathology.exercises))];
}

export type BasketItem = { exerciseId: string; note: string };

export function isInBasket(basket: BasketItem[], exerciseId: string): boolean {
  return basket.some((item) => item.exerciseId === exerciseId);
}

export function toggleInBasket(basket: BasketItem[], exerciseId: string): BasketItem[] {
  return isInBasket(basket, exerciseId)
    ? basket.filter((item) => item.exerciseId !== exerciseId)
    : [...basket, { exerciseId, note: "" }];
}

export function setBasketNote(basket: BasketItem[], exerciseId: string, note: string): BasketItem[] {
  return basket.map((item) => (item.exerciseId === exerciseId ? { ...item, note } : item));
}

export type SharePayload = {
  recipient_email: string;
  practitioner_name: string | null;
  message: string | null;
  items: { exercise_id: string; note: string | null }[];
};

export function buildSharePayload(
  basket: BasketItem[],
  form: { email: string; practitioner: string; message: string },
): SharePayload {
  const clean = (value: string) => value.trim() || null;
  return {
    recipient_email: form.email.trim(),
    practitioner_name: clean(form.practitioner),
    message: clean(form.message),
    items: basket.map((item) => ({ exercise_id: item.exerciseId, note: clean(item.note) })),
  };
}

export type ShareResult = {
  token: string;
  share_path: string;
  email_status: "sent" | "not_configured" | "failed";
};

export type SharedExercises = {
  created_at: string;
  practitioner_name: string | null;
  message: string | null;
  items: { exercise: Exercise; note: string | null }[];
};

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim());
}
