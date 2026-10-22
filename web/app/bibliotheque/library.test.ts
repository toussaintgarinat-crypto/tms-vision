import { describe, expect, it } from "vitest";
import {
  ALL_PATHOLOGIES,
  LibraryZone,
  buildSharePayload,
  exerciseIdsFor,
  isInBasket,
  isValidEmail,
  setBasketNote,
  toggleInBasket,
} from "./library";

const zone: LibraryZone = {
  id: "neck",
  label: "Cou",
  pathologies: [
    { id: "a", label: "A", exercises: ["x", "y"] },
    { id: "b", label: "B", exercises: ["y", "z"] },
  ],
};

describe("exerciseIdsFor", () => {
  it("returns the exercises of one pathology", () => {
    expect(exerciseIdsFor(zone, "b")).toEqual(["y", "z"]);
  });

  it("merges the whole zone without duplicates, keeping order", () => {
    expect(exerciseIdsFor(zone, ALL_PATHOLOGIES)).toEqual(["x", "y", "z"]);
  });

  it("returns nothing for an unknown pathology", () => {
    expect(exerciseIdsFor(zone, "nope")).toEqual([]);
  });
});

describe("basket", () => {
  it("toggles an exercise in and out", () => {
    const added = toggleInBasket([], "x");
    expect(added).toEqual([{ exerciseId: "x", note: "" }]);
    expect(isInBasket(added, "x")).toBe(true);
    expect(toggleInBasket(added, "x")).toEqual([]);
  });

  it("keeps insertion order and edits only the targeted note", () => {
    let basket = toggleInBasket(toggleInBasket([], "x"), "y");
    basket = setBasketNote(basket, "y", "10 répétitions");
    expect(basket).toEqual([
      { exerciseId: "x", note: "" },
      { exerciseId: "y", note: "10 répétitions" },
    ]);
  });
});

describe("buildSharePayload", () => {
  it("trims fields and turns blanks into null", () => {
    const payload = buildSharePayload(
      [
        { exerciseId: "x", note: "  2 fois par jour " },
        { exerciseId: "y", note: "   " },
      ],
      { email: " patient@example.com ", practitioner: " ", message: "Bonjour " },
    );
    expect(payload).toEqual({
      recipient_email: "patient@example.com",
      practitioner_name: null,
      message: "Bonjour",
      items: [
        { exercise_id: "x", note: "2 fois par jour" },
        { exercise_id: "y", note: null },
      ],
    });
  });
});

describe("isValidEmail", () => {
  it("accepts a plain address and rejects malformed ones", () => {
    expect(isValidEmail("a@b.fr")).toBe(true);
    expect(isValidEmail(" a@b.fr ")).toBe(true);
    expect(isValidEmail("a@b")).toBe(false);
    expect(isValidEmail("a b@c.fr")).toBe(false);
    expect(isValidEmail("")).toBe(false);
  });
});
