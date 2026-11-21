import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, LOCALES, LOCALE_LABELS, LOCALE_TAGS, detectLocale, isLocale } from "./locales";

describe("detectLocale", () => {
  it("prefers the saved choice", () => {
    expect(detectLocale("en", ["fr-FR"])).toBe("en");
    expect(detectLocale("fr", ["en-US"])).toBe("fr");
  });

  it("ignores an unknown saved value and reads the browser languages in order", () => {
    expect(detectLocale("xx", ["de-DE", "en-US", "fr"])).toBe("en");
    expect(detectLocale(null, ["EN-gb"])).toBe("en");
  });

  it("falls back to French when nothing matches", () => {
    expect(detectLocale(null, ["de-DE", "ja"])).toBe(DEFAULT_LOCALE);
    expect(detectLocale(null, [])).toBe(DEFAULT_LOCALE);
  });
});

describe("locale declarations", () => {
  it("gives every language a label and a BCP 47 tag", () => {
    for (const code of LOCALES) {
      expect(LOCALE_LABELS[code]).toBeTruthy();
      expect(LOCALE_TAGS[code]).toMatch(/^[a-z]{2}-[A-Z]{2}$/);
      expect(isLocale(code)).toBe(true);
    }
    expect(isLocale("xx")).toBe(false);
    expect(isLocale(null)).toBe(false);
  });
});
