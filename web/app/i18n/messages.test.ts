import { describe, expect, it } from "vitest";
import { CATALOG } from "./catalog";
import { DEFAULT_LOCALE, LOCALES } from "./locales";

const reference = CATALOG[DEFAULT_LOCALE];
const markers = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();

describe("message catalogs", () => {
  it("declares a catalog for every language", () => {
    for (const code of LOCALES) expect(CATALOG[code]).toBeDefined();
  });

  for (const code of LOCALES.filter((value) => value !== DEFAULT_LOCALE)) {
    describe(code, () => {
      it("has exactly the same keys as the reference language", () => {
        const missing = Object.keys(reference).filter((key) => !(key in CATALOG[code]));
        const extra = Object.keys(CATALOG[code]).filter((key) => !(key in reference));
        expect({ missing, extra }).toEqual({ missing: [], extra: [] });
      });

      it("keeps the same {markers} as the reference language", () => {
        const different = Object.keys(reference).filter(
          (key) => markers(reference[key]).join() !== markers(CATALOG[code][key] ?? "").join(),
        );
        expect(different).toEqual([]);
      });
    });
  }

  it("has no empty message", () => {
    for (const code of LOCALES) {
      const empty = Object.entries(CATALOG[code]).filter(([, text]) => text.trim() === "");
      expect(empty).toEqual([]);
    }
  });
});
