import { describe, expect, it } from "vitest";

import { translator } from "../i18n/catalog";
import { DEFAULT_SETTINGS, parseSettings, privacyNotice } from "./assistantSettings";

describe("parseSettings", () => {
  it("falls back to the defaults with missing or broken storage", () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("pas du json")).toEqual(DEFAULT_SETTINGS);
  });

  it("keeps valid values and ignores unexpected ones", () => {
    expect(
      parseSettings('{"engine":"server","speak":true,"mode":"guided"}'),
    ).toEqual({ engine: "server", speak: true, mode: "guided" });
    expect(parseSettings('{"engine":"autre","mode":3}')).toEqual(DEFAULT_SETTINGS);
  });
});

describe("privacyNotice", () => {
  it("says where the data goes", () => {
    const fr = translator("fr");
    expect(privacyNotice(fr, "browser", true)).toContain("navigateur");
    expect(privacyNotice(fr, "browser", true)).toContain("ne quitte pas la machine");
    expect(privacyNotice(fr, "server", false)).toContain("service de transcription");
    expect(privacyNotice(fr, "server", false)).toContain("modèle d'IA configuré");
  });

  it("says it in English too", () => {
    const en = translator("en");
    expect(privacyNotice(en, "browser", true)).toContain("browser");
    expect(privacyNotice(en, "browser", true)).toContain("does not leave the machine");
    expect(privacyNotice(en, "server", false)).toContain("transcription service");
    expect(privacyNotice(en, "server", false)).toContain("configured AI model");
    expect(privacyNotice(en, "server", false)).toContain("identify the employee");
  });
});
