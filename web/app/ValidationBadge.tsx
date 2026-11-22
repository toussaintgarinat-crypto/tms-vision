"use client";

import { useI18n } from "./i18n/I18nProvider";

// Étiquette d'un exercice (renvoyée par l'API) : qui l'a créé, et qui a validé sa version courante.
export type ValidationLabel = {
  created_by: string;
  validated_by: string | null;
  validated_on: string | null;
  fingerprint: string;
};

export function ValidationBadge({ label }: { label: ValidationLabel }) {
  const { t, tag } = useI18n();
  const validated = label.validated_by !== null && label.validated_on !== null;
  const date = validated ? new Date(label.validated_on as string).toLocaleDateString(tag) : "";
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="text-gray-600">{t("validation.createdBy", { name: label.created_by })}</span>
      <span
        className={`rounded px-1.5 py-0.5 font-semibold ${
          validated ? "bg-emerald-100 text-emerald-900" : "bg-amber-100 text-amber-900"
        }`}
      >
        {validated
          ? t("validation.validatedBy", { name: label.validated_by as string, date })
          : t("validation.notValidated")}
      </span>
    </span>
  );
}
