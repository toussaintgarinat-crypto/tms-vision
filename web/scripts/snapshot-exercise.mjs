#!/usr/bin/env node
// Sauvegarde quelques images fixes d'un exercice (aux instants demandés) pour le vérifier à
// l'œil sans rendre toute la vidéo. Même page de rendu que render-exercise.mjs.
//
// Usage :
//   node scripts/snapshot-exercise.mjs --definition <exercice.json> --out <dossier>
//        [--times 0,5,10] [--base-url http://localhost:3000] [--gpu]
// Par défaut : une image à chaque pose clé de l'exercice.
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright-core";

function parseArgs(argv) {
  const options = { baseUrl: "http://localhost:3000", gpu: false, times: null };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const value = () => {
      if (i + 1 >= argv.length) throw new Error(`Valeur manquante pour ${arg}.`);
      return argv[++i];
    };
    if (arg === "--definition") options.definition = value();
    else if (arg === "--out") options.out = value();
    else if (arg === "--times") options.times = value().split(",").map(Number);
    else if (arg === "--base-url") options.baseUrl = value().replace(/\/$/, "");
    else if (arg === "--gpu") options.gpu = true;
    else throw new Error(`Option inconnue : ${arg}`);
  }
  if (!options.definition || !options.out) {
    throw new Error("Usage : snapshot-exercise.mjs --definition <fichier.json> --out <dossier> [--times 0,5,10]");
  }
  return options;
}

const options = parseArgs(process.argv.slice(2));
const exercise = JSON.parse(fs.readFileSync(options.definition, "utf8"));
const times = options.times ?? exercise.keyframes.map((keyframe) => keyframe.t);
fs.mkdirSync(options.out, { recursive: true });

const args = options.gpu ? [] : ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"];
if (typeof process.getuid === "function" && process.getuid() === 0) args.push("--no-sandbox");
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args });
try {
  const page = await browser.newPage({ viewport: { width: 1000, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto(`${options.baseUrl}/render/${encodeURIComponent(exercise.id)}`);
  await page.waitForFunction(() => window.__tmsRender, null, { timeout: 120000 });
  await page.evaluate((definition) => window.__tmsRender.load(definition), exercise);
  for (const t of times) {
    await page.evaluate((time) => window.__tmsRender.setTime(time), t);
    const file = path.join(options.out, `${exercise.id}-t${String(t).padStart(3, "0")}.png`);
    await page.locator("#stage").screenshot({ path: file, type: "png" });
    process.stderr.write(`${file}\n`);
  }
  if (errors.length > 0) throw new Error(`Erreurs dans la page de rendu : ${errors.join(" | ")}`);
} finally {
  await browser.close();
}
