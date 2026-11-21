import { describe, expect, it } from "vitest";

import { translator } from "../i18n/catalog";
import { AuthStatus, isPublicPath, mustLogIn, problemText, readProblem } from "./authFetch";

const status = (patch: Partial<AuthStatus>): AuthStatus => ({
  auth_required: true,
  setup_required: false,
  authenticated: false,
  user: null,
  ...patch,
});

describe("mustLogIn", () => {
  it("sends anonymous visitors to the login page once accounts are required", () => {
    expect(mustLogIn(status({}), "/bilans")).toBe(true);
    expect(mustLogIn(status({}), "/")).toBe(true);
  });

  it("leaves the login page, the patient page and the render page open", () => {
    expect(mustLogIn(status({}), "/connexion")).toBe(false);
    expect(mustLogIn(status({}), "/bibliotheque/envoi/abc")).toBe(false);
    expect(mustLogIn(status({}), "/render/neck")).toBe(false);
    expect(isPublicPath("/bibliotheque")).toBe(false);
  });

  it("does nothing while the status is unknown, when logged in, or when accounts are not required", () => {
    expect(mustLogIn(null, "/bilans")).toBe(false);
    expect(mustLogIn(status({ authenticated: true }), "/bilans")).toBe(false);
    expect(mustLogIn(status({ auth_required: false }), "/bilans")).toBe(false);
  });
});

describe("readProblem and problemText", () => {
  const fr = translator("fr");
  const en = translator("en");

  it("reads a structured detail", () => {
    const problem = readProblem({ detail: { message: "Trop", code: "too_many_attempts", retry_after: 7 } });
    expect(problem).toEqual({ code: "too_many_attempts", message: "Trop", retryAfter: 7 });
    expect(problemText(problem, en, "x")).toBe("Too many attempts: wait 7 s before trying again.");
    expect(problemText(problem, fr, "x")).toBe("Trop de tentatives : patientez 7 s avant de réessayer.");
  });

  it("falls back to the server message for an unknown code, then to the default text", () => {
    expect(problemText(readProblem({ detail: { message: "Msg serveur", code: "inconnu" } }), en, "x")).toBe("Msg serveur");
    expect(problemText(readProblem({ detail: "Texte simple" }), en, "x")).toBe("Texte simple");
    expect(problemText(readProblem(null), en, "défaut")).toBe("défaut");
  });
});
