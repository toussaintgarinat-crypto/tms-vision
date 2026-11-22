import { describe, expect, it } from "vitest";
import { MAX_FILE_BYTES, readBundle, summarize } from "./exchange";

const good = JSON.stringify({ format: "tms-vision-fiches", version: 1, sheets: [{ content: {} }, { content: {} }] });

describe("readBundle", () => {
  it("accepts an exchange file and counts its sheets", () => {
    const result = readBundle(good);
    expect(result.ok && result.count).toBe(2);
  });

  it("refuses what is not an exchange file", () => {
    expect(readBundle("pas du json")).toEqual({ ok: false, reason: "notJson" });
    expect(readBundle("{}")).toEqual({ ok: false, reason: "notBundle" });
    expect(readBundle(JSON.stringify({ format: "autre", version: 1, sheets: [] }))).toEqual({ ok: false, reason: "notBundle" });
    expect(readBundle(JSON.stringify({ format: "tms-vision-fiches", version: 1, sheets: [] }))).toEqual({ ok: false, reason: "empty" });
    expect(readBundle("null")).toEqual({ ok: false, reason: "notBundle" });
  });

  it("refuses a file that is far too big before parsing it", () => {
    expect(readBundle(good, MAX_FILE_BYTES + 1)).toEqual({ ok: false, reason: "tooBig" });
  });
});

describe("summarize", () => {
  it("counts the report by status", () => {
    expect(
      summarize([
        { title: "a", status: "imported" },
        { title: "b", status: "imported" },
        { title: "c", status: "duplicate" },
        { title: "d", status: "invalid", error: "x" },
      ]),
    ).toEqual({ imported: 2, duplicate: 1, invalid: 1 });
  });
});
