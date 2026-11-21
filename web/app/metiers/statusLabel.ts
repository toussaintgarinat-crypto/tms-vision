import type { TFunction } from "../i18n/translate";
import type { MetierModel } from "./types";

// Mention d'état d'un modèle de métier : validé, modèle du praticien ou brouillon.
export function statusLabel(t: TFunction, model: MetierModel): string {
  if (model.status === "validated") {
    return t("metiers.status.validated", { by: model.validated_by ?? t("metiers.status.aProfessional") });
  }
  if (model.origin === "custom") return t("metiers.status.custom");
  return t(model.source === "ai" ? "metiers.status.draftAi" : "metiers.status.draft");
}
