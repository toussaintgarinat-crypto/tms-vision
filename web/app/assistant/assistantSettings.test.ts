import { describe, expect, it } from "vitest";

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
    expect(privacyNotice("browser", true)).toContain("navigateur");
    expect(privacyNotice("browser", true)).toContain("ne quitte pas la machine");
    expect(privacyNotice("server", false)).toContain("service de transcription");
    expect(privacyNotice("server", false)).toContain("modèle d'IA configuré");
  });
});
