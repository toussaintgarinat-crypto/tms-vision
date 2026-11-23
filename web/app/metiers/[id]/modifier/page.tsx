"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useI18n } from "../../../i18n/I18nProvider";
import { MetierForm } from "../../MetierForm";
import type { MetierModel } from "../../types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function EditMetierPage() {
  const { t } = useI18n();
  const id = decodeURIComponent(useParams<{ id: string }>().id);
  const [model, setModel] = useState<MetierModel | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    fetch(`${API_URL}/metiers`)
      .then((response) => (response.ok ? (response.json() as Promise<MetierModel[]>) : Promise.reject(new Error("load"))))
      .then((all) => {
        const found = all.find((entry) => entry.id === id && entry.origin === "custom");
        if (found) setModel(found);
        else setFailed(true);
      })
      .catch(() => setFailed(true));
  }, [id]);

  if (failed) return <main className="p-6 text-sm text-red-700">{t("metiers.error.load")}</main>;
  if (!model) return <main className="p-6 text-sm text-gray-600">{t("live.loading")}</main>;
  return <MetierForm model={model} />;
}
