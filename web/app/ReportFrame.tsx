"use client";

import { ReactNode, useEffect, useRef, useState } from "react";

import { Exercise } from "./exercisePose";
import { LiveExercise } from "./LiveExercise";
import { useI18n } from "./i18n/I18nProvider";
import { DRAFT_BADGE_KEY, FICHE_BADGE_KEY, capsuleVideoSrc } from "./programFormat";
import { ProgramItem } from "./ProgramList";
import { blobToDataUrl, buildStandaloneHtml, reportFileName } from "./reportExport";
import { REPORT_CSS } from "./reportStyles";
import { ExerciseStills, Still, StillsRenderer } from "./StillsRenderer";
import { MUSCLE_MODEL_CREDIT } from "./muscleModel";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Mode = "carousel" | "animation" | "video";
const MODES: Mode[] = ["carousel", "animation", "video"];

// À l'impression, l'application (menu, barre d'outils) disparaît : seul le compte rendu reste.
const PRINT_CSS = `@media print{header,.tms-toolbar{display:none!important}}`;

function Carousel({ steps, title }: { steps: Still[]; title: string }) {
  const { t } = useI18n();
  const [index, setIndex] = useState(0);
  const count = steps.length;
  return (
    <div className="carousel">
      {steps.map((step, position) => (
        <div key={step.t} className={`step${position === index ? " active" : ""}`}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={step.image} alt={t("report.stepAlt", { title, step: position + 1 })} />
          <p>
            <strong>
              {position + 1}/{count}
            </strong>{" "}
            {step.text}
          </p>
        </div>
      ))}
      <div className="nav">
        <button type="button" data-dir="-1" onClick={() => setIndex((index - 1 + count) % count)}>
          ←
        </button>
        <span className="count">
          {index + 1} / {count}
        </span>
        <button type="button" data-dir="1" onClick={() => setIndex((index + 1) % count)}>
          →
        </button>
      </div>
    </div>
  );
}

// Anime l'exercice seulement tant que son bloc est à l'écran : un compte rendu de 10 exercices
// ne garde ainsi que 1 ou 2 mannequins 3D (contextes WebGL) en vie, au lieu de 10 qui tournent
// ensemble et ralentissent la page. Les blocs hors écran gardent leur place (hauteur minimale).
function LazyLive({ exerciseId }: { exerciseId: string }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState(() => typeof IntersectionObserver === "undefined");

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {
      rootMargin: "150px",
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} style={{ minHeight: 320 }}>
      {visible && <LiveExercise exerciseId={exerciseId} />}
    </div>
  );
}

function ExerciseBlock({
  item,
  exercise,
  stills,
  animated,
}: {
  item: ProgramItem;
  exercise: Exercise;
  stills: Still[];
  animated: boolean;
}) {
  const { t } = useI18n();
  const videoSrc = capsuleVideoSrc(item.capsule, API_URL);
  return (
    <section className="ex">
      <h3>
        {item.rank}. {exercise.title}
        {exercise.fiche && <span className="badge fiche">{t(FICHE_BADGE_KEY)}</span>}
        {item.capsule.status === "draft" && !exercise.fiche && (
          <span className="badge">{t(DRAFT_BADGE_KEY)}</span>
        )}
        {exercise.position && exercise.position !== "standing" && (
          <span className="badge pos">{t(`position.${exercise.position}`)}</span>
        )}
      </h3>
      <p className="muted">{item.reason}</p>
      <p>{exercise.description}</p>
      <div className={`stills${videoSrc ? "" : " force"}`}>
        {stills.length > 0 && <Carousel steps={stills} title={exercise.title} />}
      </div>
      {videoSrc && (
        <div className="video">
          <video controls preload="metadata" src={videoSrc} />
        </div>
      )}
      {animated && (
        <div className="live">
          <LazyLive exerciseId={exercise.id} />
        </div>
      )}
    </section>
  );
}

type Loaded = { key: string; exercises: Exercise[] | null };

// Cadre commun des comptes rendus anonymes (bilan de poste, analyse seule) : le contenu propre au
// compte rendu (`children`), puis le programme d'étirements avec, au choix, des carrousels d'images,
// l'animation 3D ou la vidéo. Export : PDF (impression, avec les carrousels) ou fichier HTML
// autonome (carrousels ou vidéos). Rien ici ne nomme le salarié ni l'analyse d'origine.
export function ReportFrame({
  title,
  program,
  children,
}: {
  title: string;
  program: ProgramItem[];
  children: ReactNode;
}) {
  const { t, locale } = useI18n();
  const key = program.map((item) => item.capsule.id).join(",");
  const [mode, setMode] = useState<Mode>("carousel");
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [stillsState, setStillsState] = useState<{ key: string; stills: ExerciseStills } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (key === "") return;
    let cancelled = false;
    Promise.all(
      key.split(",").map((id) =>
        fetch(`${API_URL}/exercises/${encodeURIComponent(id)}`).then((response) => {
          if (!response.ok) throw new Error(t("bilans.error.httpStatus", { status: response.status }));
          return response.json() as Promise<Exercise>;
        }),
      ),
    )
      .then((exercises) => {
        if (!cancelled) setLoaded({ key, exercises });
      })
      .catch(() => {
        if (!cancelled) setLoaded({ key, exercises: null });
      });
    return () => {
      cancelled = true;
    };
  }, [key, t]);

  const exercises = loaded && loaded.key === key ? loaded.exercises : undefined;
  const stills = stillsState && stillsState.key === key ? stillsState.stills : undefined;
  const ready = key === "" || (exercises !== undefined && exercises !== null && stills !== undefined);
  const failed = key !== "" && exercises === null;

  async function download(kind: "carousel" | "video") {
    const root = containerRef.current;
    if (!root) return;
    setBusy(kind);
    setError(null);
    try {
      const clone = root.cloneNode(true) as HTMLElement;
      clone.querySelectorAll(".live").forEach((node) => node.remove());
      clone.setAttribute("data-mode", kind);
      clone.querySelectorAll(".carousel").forEach((carousel) => {
        const steps = carousel.querySelectorAll(".step");
        steps.forEach((step, position) => step.classList.toggle("active", position === 0));
        const counter = carousel.querySelector(".count");
        if (counter) counter.textContent = `1 / ${steps.length}`;
      });
      const videos = Array.from(clone.querySelectorAll("video"));
      if (kind === "video") {
        for (const video of videos) {
          const response = await fetch(video.getAttribute("src") ?? "");
          if (!response.ok) throw new Error(t("report.error.videoMissing", { status: response.status }));
          video.setAttribute("src", await blobToDataUrl(await response.blob()));
          video.removeAttribute("preload");
        }
      } else {
        videos.forEach((video) => video.parentElement?.remove());
      }
      const blob = new Blob([buildStandaloneHtml(title, clone.outerHTML, locale)], { type: "text/html" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = reportFileName(kind, new Date(), t("report.filePrefix"));
      link.click();
      URL.revokeObjectURL(link.href);
    } catch {
      setError(t("report.error.html"));
    } finally {
      setBusy(null);
    }
  }

  const button = "rounded border border-black px-3 py-1 text-sm disabled:opacity-50";

  return (
    <div className="flex flex-col gap-4">
      <style>{PRINT_CSS}</style>
      <div className="tms-toolbar flex flex-col gap-3 rounded border p-4">
        <fieldset className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
          <legend className="mb-1 font-medium">{t("report.display")}</legend>
          {MODES.map((value) => (
            <label key={value} className="flex items-center gap-1">
              <input type="radio" name="report-mode" checked={mode === value} onChange={() => setMode(value)} />
              {t(`report.mode.${value}`)}
            </label>
          ))}
        </fieldset>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={button} disabled={!ready} onClick={() => window.print()}>
            {t("report.savePdf")}
          </button>
          <button type="button" className={button} disabled={!ready || busy !== null} onClick={() => download("carousel")}>
            {t("report.htmlCarousels")}
          </button>
          <button type="button" className={button} disabled={!ready || busy !== null} onClick={() => download("video")}>
            {busy === "video" ? t("report.preparingVideos") : t("report.htmlVideos")}
          </button>
        </div>
        <p className="text-xs text-gray-600">
          {t("report.pdfHelp")}
          {!ready && !failed && ` ${t("report.preparingImages")}`}
        </p>
        {failed && <p className="text-sm text-red-600">{t("report.error.exercises")}</p>}
        {error && <p className="text-sm text-red-600">{error}</p>}
      </div>

      {exercises && stills === undefined && (
        <StillsRenderer
          key={key}
          exercises={exercises}
          onDone={(result) => setStillsState({ key, stills: result })}
        />
      )}

      <div ref={containerRef} className="tms-report" data-mode={mode}>
        <style>{REPORT_CSS}</style>
        {children}
        <h2>{t("report.program")}</h2>
        {program.length === 0 && (
          <p className="muted">
            {t("report.noProgram")}
          </p>
        )}
        {ready &&
          exercises &&
          stills &&
          program.map((item) => {
            const exercise = exercises.find((candidate) => candidate.id === item.capsule.id);
            return exercise ? (
              <ExerciseBlock
                key={item.capsule.id}
                item={item}
                exercise={exercise}
                stills={stills[exercise.id] ?? []}
                animated={mode === "animation"}
              />
            ) : null;
          })}
        <footer className="muted">
          <p>
            {t("report.footer")}
          </p>
          <p>{MUSCLE_MODEL_CREDIT}</p>
        </footer>
      </div>
    </div>
  );
}
