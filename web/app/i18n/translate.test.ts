import { describe, expect, it } from "vitest";
import { interpolate, translate } from "./translate";

const catalog = {
  fr: { hello: "Bonjour {name}", onlyFr: "Seulement en français", twice: "{n} sur {n}" },
  en: { hello: "Hello {name}" },
};

describe("interpolate", () => {
  it("replaces named markers, numbers included", () => {
    expect(interpolate("Étape {step} / {total}", { step: 2, total: 5 })).toBe("Étape 2 / 5");
    expect(interpolate("{n} sur {n}", { n: 3 })).toBe("3 sur 3");
  });

  it("leaves a marker without a value as is, so the omission is visible", () => {
    expect(interpolate("Bonjour {name}", {})).toBe("Bonjour {name}");
    expect(interpolate("Bonjour {name}")).toBe("Bonjour {name}");
  });

  it("does not treat the value as a template", () => {
    expect(interpolate("A {x}", { x: "{y}" })).toBe("A {y}");
  });
});

describe("translate", () => {
  it("uses the requested language", () => {
    expect(translate(catalog, "en", "hello", { name: "Léa" })).toBe("Hello Léa");
    expect(translate(catalog, "fr", "hello", { name: "Léa" })).toBe("Bonjour Léa");
  });

  it("falls back to French, then to the key itself", () => {
    expect(translate(catalog, "en", "onlyFr")).toBe("Seulement en français");
    expect(translate(catalog, "en", "absent.key")).toBe("absent.key");
  });
});
