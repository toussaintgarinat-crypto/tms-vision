import { describe, expect, it } from "vitest";
import { NAV_ITEMS, isActive, isMenuHidden } from "./navItems";

describe("isActive", () => {
  it("only matches the home page exactly for /", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/historique", "/")).toBe(false);
  });

  it("matches a section and its sub-pages, not a sibling with the same prefix", () => {
    expect(isActive("/historique", "/historique")).toBe(true);
    expect(isActive("/historique/abc", "/historique")).toBe(true);
    expect(isActive("/historiques", "/historique")).toBe(false);
    expect(isActive("/bibliotheque", "/bilans")).toBe(false);
  });

  it("marks exactly one menu item for each known page", () => {
    for (const item of NAV_ITEMS) {
      expect(NAV_ITEMS.filter((other) => isActive(item.href, other.href))).toEqual([item]);
    }
  });
});

describe("isMenuHidden", () => {
  it("hides the menu on the render page and on the patient page", () => {
    expect(isMenuHidden("/render/neck-lateral-stretch")).toBe(true);
    expect(isMenuHidden("/bibliotheque/envoi/abc123")).toBe(true);
  });

  it("keeps it on the practitioner pages", () => {
    expect(isMenuHidden("/")).toBe(false);
    expect(isMenuHidden("/bibliotheque")).toBe(false);
    expect(isMenuHidden("/historique/abc")).toBe(false);
  });
});
