"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { useI18n } from "../../../i18n/I18nProvider";
import { LanguageSwitcher } from "../../../i18n/LanguageSwitcher";
import { ExerciseCarousel } from "../../ExerciseCarousel";
import { API_URL, SharedExercises } from "../../library";

// Page ouverte par le patient depuis le lien de l'email : l'adresse (jeton aléatoire) en est
// l'unique protection, comme pour un lien de partage.
export default function SharedExercisesPage() {
  const { t } = useI18n();
  const { token } = useParams<{ token: string }>();
  const [loaded, setLoaded] = useState<{ token: string; share: SharedExercises } | null>(null);
  const [failedFor, setFailedFor] = useState<{ token: string; notFound: boolean } | null>(null);
  const [index, setIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API_URL}/library/shares/${encodeURIComponent(token)}`)
      .then((response) => {
        if (response.status === 404) {
          if (!cancelled) setFailedFor({ token, notFound: true });
          return null;
        }
        if (!response.ok) throw new Error(`Erreur ${response.status}`);
        return response.json() as Promise<SharedExercises>;
      })
      .then((share) => {
        if (!cancelled && share) setLoaded({ token, share });
      })
      .catch(() => {
        if (!cancelled) setFailedFor({ token, notFound: false });
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  const share = loaded?.token === token ? loaded.share : null;
  const failure = failedFor?.token === token ? failedFor : null;

  if (failure) {
    return (
      <main className="mx-auto w-full max-w-xl flex-1 p-6">
        <p role="alert" className="text-sm text-red-700">
          {failure.notFound ? t("share.notFound") : t("share.loadFailed")}
        </p>
      </main>
    );
  }
  if (!share) {
    return <main className="mx-auto w-full max-w-xl flex-1 p-6 text-sm text-zinc-500">{t("share.loading")}</main>;
  }

  const notes = new Map(share.items.map((item) => [item.exercise.id, item.note]));

  return (
    <main className="mx-auto w-full max-w-xl flex-1 p-4 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <h1 className="text-2xl font-bold">{t("share.title")}</h1>
        <LanguageSwitcher />
      </div>
      {share.practitioner_name && (
        <p className="text-sm text-zinc-600 dark:text-zinc-400">{t("share.from", { name: share.practitioner_name })}</p>
      )}
      {share.message && (
        <p className="mb-4 mt-3 whitespace-pre-line rounded-lg bg-zinc-100 p-3 text-sm dark:bg-zinc-800">
          {share.message}
        </p>
      )}
      <ExerciseCarousel
        exercises={share.items.map((item) => item.exercise)}
        index={index}
        onIndexChange={setIndex}
        footer={(exercise) =>
          notes.get(exercise.id) ? (
            <p className="text-sm">
              <span className="font-semibold">{t("share.todo")} </span>
              {notes.get(exercise.id)}
            </p>
          ) : null
        }
      />
      <p className="mt-4 text-xs text-zinc-500">
        {t("share.disclaimer")}
      </p>
    </main>
  );
}
