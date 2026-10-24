import { describe, expect, it } from "vitest";

import { childrenOf, descendantIds, folderOptions, folderPath, totalCount } from "./folderTree";
import { BilanFolder } from "./types";

function folder(id: string, name: string, parent_id: string | null = null): BilanFolder {
  return { id, name, parent_id, created_at: "2026-01-01T00:00:00+00:00" };
}

const FOLDERS = [
  folder("acme", "Acme"),
  folder("prod", "Production", "acme"),
  folder("soud", "Soudure", "prod"),
  folder("rh", "RH", "acme"),
  folder("roche", "Boulangerie Roche"),
];

describe("childrenOf", () => {
  it("lists the roots, then the direct sub-folders, alphabetically", () => {
    expect(childrenOf(FOLDERS, null).map((f) => f.id)).toEqual(["acme", "roche"]);
    expect(childrenOf(FOLDERS, "acme").map((f) => f.id)).toEqual(["prod", "rh"]);
    expect(childrenOf(FOLDERS, "soud")).toEqual([]);
  });

  it("treats a folder whose parent is missing as a root folder", () => {
    const orphan = folder("o", "Orpheline", "gone");
    expect(childrenOf([...FOLDERS, orphan], null).map((f) => f.id)).toContain("o");
  });
});

describe("descendantIds", () => {
  it("collects every level below a folder, without the folder itself", () => {
    expect([...descendantIds(FOLDERS, "acme")].sort()).toEqual(["prod", "rh", "soud"]);
    expect(descendantIds(FOLDERS, "soud").size).toBe(0);
  });

  it("does not loop on a corrupted cycle", () => {
    const cycle = [folder("a", "A", "b"), folder("b", "B", "a")];
    expect(descendantIds(cycle, "a").size).toBeLessThanOrEqual(2);
  });
});

describe("folderPath and folderOptions", () => {
  it("builds the readable path from the company down to the post", () => {
    expect(folderPath(FOLDERS, "soud")).toBe("Acme › Production › Soudure");
    expect(folderPath(FOLDERS, "roche")).toBe("Boulangerie Roche");
  });

  it("lists parents before children and can exclude a folder with its content", () => {
    expect(folderOptions(FOLDERS).map((o) => o.label)).toEqual([
      "Acme",
      "Acme › Production",
      "Acme › Production › Soudure",
      "Acme › RH",
      "Boulangerie Roche",
    ]);
    expect(folderOptions(FOLDERS, "prod").map((o) => o.id)).toEqual(["acme", "rh", "roche"]);
  });
});

describe("totalCount", () => {
  it("adds the bilans of every sub-folder", () => {
    const counts = new Map([["acme", 1], ["prod", 2], ["soud", 3], ["roche", 5]]);
    expect(totalCount(FOLDERS, "acme", counts)).toBe(6);
    expect(totalCount(FOLDERS, "prod", counts)).toBe(5);
    expect(totalCount(FOLDERS, "rh", counts)).toBe(0);
  });
});
