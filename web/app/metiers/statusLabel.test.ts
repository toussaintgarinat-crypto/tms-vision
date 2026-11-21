import { describe, expect, it } from "vitest";

import { translator } from "../i18n/catalog";
import { statusLabel } from "./statusLabel";
import { DOMAINS, domainKey, MetierModel } from "./types";

const base: MetierModel = {
  id: "m",
  title: "Métier",
  description: "",
  origin: "library",
  status: "draft",
  source: "human",
  validated_by: null,
  workday_hours: 8,
  tasks: [],
};

describe("statusLabel", () => {
  const fr = translator("fr");
  const en = translator("en");

  it("says who validated a validated model", () => {
    const model = { ...base, status: "validated" as const, validated_by: "Dr Martin" };
    expect(statusLabel(fr, model)).toBe("Validé par Dr Martin");
    expect(statusLabel(en, model)).toBe("Validated by Dr Martin");
  });

  it("falls back to a generic professional", () => {
    const model = { ...base, status: "validated" as const };
    expect(statusLabel(fr, model)).toBe("Validé par un professionnel");
    expect(statusLabel(en, model)).toBe("Validated by a professional");
  });

  it("tells custom models, drafts and AI drafts apart", () => {
    expect(statusLabel(en, { ...base, origin: "custom" })).toBe("Practitioner's template");
    expect(statusLabel(en, base)).toBe("Draft, to be validated");
    expect(statusLabel(en, { ...base, source: "ai" })).toBe("AI-generated draft, to be validated");
    expect(statusLabel(fr, { ...base, source: "ai" })).toBe("Brouillon généré par IA, à valider");
  });
});

describe("domain names", () => {
  it("are translated for every domain", () => {
    expect(DOMAINS.filter((domain) => translator("en")(domainKey(domain)) === domainKey(domain))).toEqual([]);
  });
});
