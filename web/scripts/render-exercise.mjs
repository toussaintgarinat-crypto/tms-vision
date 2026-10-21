#!/usr/bin/env node
// Rend la vidéo d'un exercice d'étirement : pilote la page /render/<id> (avatar 3D
// animé par poses clés) image par image avec Chromium sans écran, et envoie les images
// à ffmpeg. Voir docs/superpowers/plans/2026-10-21-generation-modules-etirement-plan.md.
//
// Usage :
//   node scripts/render-exercise.mjs --definition <exercice.json> --out <video.mp4>
//        [--fps 15] [--base-url http://localhost:3000] [--gpu]
//
// Prérequis : le serveur Next.js tourne à --base-url (npm run dev, ou npm run build &&
// npm start), `ffmpeg` est installé, et Chromium est disponible pour Playwright
// (`npx playwright-core install chromium`, ou variable CHROMIUM_PATH).
//
// Par défaut le rendu WebGL est logiciel (SwiftShader) : plus lent mais reproductible
// d'une exécution à l'autre. `--gpu` utilise le processeur graphique de la machine.
//
// Codes de sortie : 0 succès ; 2 usage ; 3 Chromium ou ffmpeg introuvable ;
// 4 serveur Next.js injoignable ; 1 autre erreur.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { chromium } from "playwright-core";

const EXIT_USAGE = 2;
const EXIT_MISSING_TOOL = 3;
const EXIT_NO_SERVER = 4;

class CliError extends Error {
  constructor(message, code) {
    super(message);
    this.code = code;
  }
}

function parseArgs(argv) {
  const options = { fps: 15, baseUrl: "http://localhost:3000", gpu: false };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = () => {
      if (i + 1 >= argv.length) throw new CliError(`Valeur manquante pour ${arg}.`, EXIT_USAGE);
      return argv[++i];
    };
    if (arg === "--definition") options.definition = value();
    else if (arg === "--out") options.out = value();
    else if (arg === "--fps") options.fps = Number(value());
    else if (arg === "--base-url") options.baseUrl = value().replace(/\/$/, "");
    else if (arg === "--gpu") options.gpu = true;
    else throw new CliError(`Option inconnue : ${arg}`, EXIT_USAGE);
  }
  if (!options.definition || !options.out) {
    throw new CliError("Usage : render-exercise.mjs --definition <fichier.json> --out <video.mp4> [--fps 15] [--base-url URL] [--gpu]", EXIT_USAGE);
  }
  if (!Number.isFinite(options.fps) || options.fps < 1 || options.fps > 60) {
    throw new CliError("--fps doit être un nombre compris entre 1 et 60.", EXIT_USAGE);
  }
  return options;
}

async function assertServerReachable(baseUrl) {
  try {
    const response = await fetch(`${baseUrl}/render/ping`, { signal: AbortSignal.timeout(15000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
  } catch (error) {
    throw new CliError(
      `Serveur Next.js injoignable à ${baseUrl} (${error.message}). Lancez-le avec « npm run dev » dans web/.`,
      EXIT_NO_SERVER,
    );
  }
}

// Échoue tout de suite, avant de lancer Chromium, si ffmpeg n'est pas installé.
function assertFfmpegInstalled() {
  return new Promise((resolve, reject) => {
    const probe = spawn("ffmpeg", ["-version"], { stdio: "ignore" });
    probe.on("error", (error) => {
      reject(
        error.code === "ENOENT"
          ? new CliError("ffmpeg est introuvable : installez-le (par exemple « brew install ffmpeg »).", EXIT_MISSING_TOOL)
          : error,
      );
    });
    probe.on("close", resolve);
  });
}

function startFfmpeg(fps, out) {
  const child = spawn(
    "ffmpeg",
    [
      "-y", "-loglevel", "error",
      "-f", "image2pipe", "-framerate", String(fps), "-vcodec", "png", "-i", "-",
      "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
      // Un seul fil : sortie reproductible d'une exécution à l'autre.
      "-threads", "1",
      "-movflags", "+faststart", "-r", String(fps),
      out,
    ],
    { stdio: ["pipe", "ignore", "pipe"] },
  );
  let stderr = "";
  child.stderr.on("data", (chunk) => (stderr += chunk));
  const done = new Promise((resolve, reject) => {
    child.on("error", (error) => {
      if (error.code === "ENOENT") {
        reject(new CliError("ffmpeg est introuvable : installez-le (par exemple « brew install ffmpeg »).", EXIT_MISSING_TOOL));
      } else reject(error);
    });
    child.on("close", (code) => {
      if (code === 0) resolve();
      else reject(new Error(`ffmpeg a échoué (code ${code}) : ${stderr.trim()}`));
    });
  });
  // Si ffmpeg meurt, l'échec est rapporté par `done` ; l'erreur d'écriture (EPIPE) qui
  // en découle ne doit pas faire planter le processus.
  child.stdin.on("error", () => {});
  // Évite un rejet non géré si ffmpeg meurt avant qu'on attende `done`.
  done.catch(() => {});
  return { child, done };
}

// Attend la fin de l'écoulement des données, ou l'échec de ffmpeg : sans ce second cas,
// un ffmpeg mort ne déclencherait jamais « drain » et la boucle attendrait indéfiniment.
async function writeFrame(stdin, buffer, ffmpegDone) {
  if (!stdin.write(buffer)) {
    await Promise.race([new Promise((resolve) => stdin.once("drain", resolve)), ffmpegDone]);
  }
}

async function launchBrowser({ gpu }) {
  const args = gpu ? [] : ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
  // Chromium refuse de démarrer en root (conteneurs) sans ce drapeau.
  if (typeof process.getuid === "function" && process.getuid() === 0) args.push("--no-sandbox");
  try {
    return await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args });
  } catch (error) {
    throw new CliError(
      `Chromium est introuvable ou n'a pas pu démarrer (${error.message.split("\n")[0]}). ` +
        "Installez-le avec « npx playwright-core install chromium » ou définissez CHROMIUM_PATH.",
      EXIT_MISSING_TOOL,
    );
  }
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  const exercise = JSON.parse(fs.readFileSync(options.definition, "utf8"));
  const frameCount = Math.round(exercise.duration_seconds * options.fps);

  await assertFfmpegInstalled();
  await assertServerReachable(options.baseUrl);
  const ffmpeg = startFfmpeg(options.fps, options.out);

  let browser;
  try {
    browser = await launchBrowser(options);
    // Fenêtre plus grande que la scène (640 px) : les indicateurs de développement de
    // Next.js, fixés au bas de la fenêtre, restent hors de la zone capturée.
    const page = await browser.newPage({ viewport: { width: 1000, height: 1000 } });
    const pageErrors = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));

    await page.goto(`${options.baseUrl}/render/${encodeURIComponent(exercise.id)}`);
    await page.waitForFunction(() => window.__tmsRender, null, { timeout: 120000 });
    await page.evaluate((definition) => window.__tmsRender.load(definition), exercise);

    const stage = page.locator("#stage");
    let nextReport = 0.1;
    for (let i = 0; i < frameCount; i++) {
      await page.evaluate((t) => window.__tmsRender.setTime(t), i / options.fps);
      await writeFrame(ffmpeg.child.stdin, await stage.screenshot({ type: "png" }), ffmpeg.done);
      if ((i + 1) / frameCount >= nextReport) {
        process.stderr.write(`  ${Math.round(((i + 1) / frameCount) * 100)} % (${i + 1}/${frameCount} images)\n`);
        nextReport += 0.1;
      }
    }
    if (pageErrors.length > 0) {
      throw new Error(`Erreurs dans la page de rendu : ${pageErrors.join(" | ")}`);
    }
    ffmpeg.child.stdin.end();
    await ffmpeg.done;
  } catch (error) {
    ffmpeg.child.stdin.destroy();
    ffmpeg.child.kill();
    throw error;
  } finally {
    if (browser) await browser.close();
  }
  process.stderr.write(`Vidéo écrite : ${options.out} (${frameCount} images, ${options.fps} images/s)\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exit(error instanceof CliError ? error.code : 1);
});
