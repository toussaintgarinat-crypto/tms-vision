// Les requêtes vers l'API portent le cookie de session (même quand le site et l'API sont sur deux
// ports, en développement). Une réponse « connexion requise » prévient le fournisseur d'authentification,
// qui renvoie vers la page de connexion.

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Pages ouvertes sans compte : la connexion, et la page que reçoit le patient par email.
export function isPublicPath(pathname: string): boolean {
  return (
    pathname === "/connexion" ||
    pathname.startsWith("/bibliotheque/envoi/") ||
    pathname === "/render" ||
    pathname.startsWith("/render/")
  );
}

export type AuthStatus = {
  auth_required: boolean;
  setup_required: boolean;
  authenticated: boolean;
  user: AuthUser | null;
};

export type AuthUser = {
  id: string;
  email: string;
  name: string;
  roles: string[];
  language: string | null;
  active: boolean;
};

// Faut-il renvoyer vers la page de connexion ?
export function mustLogIn(status: AuthStatus | null, pathname: string): boolean {
  return status !== null && status.auth_required && !status.authenticated && !isPublicPath(pathname);
}

export type ApiProblem = { code: string | null; message: string | null; retryAfter: number | null };

// Lit l'erreur d'une réponse de l'API : `detail` est un texte, ou un objet {message, code, retry_after}.
export function readProblem(body: unknown): ApiProblem {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return { code: null, message: detail, retryAfter: null };
  if (detail && typeof detail === "object") {
    const { message, code, retry_after: retryAfter } = detail as Record<string, unknown>;
    return {
      code: typeof code === "string" ? code : null,
      message: typeof message === "string" ? message : null,
      retryAfter: typeof retryAfter === "number" ? retryAfter : null,
    };
  }
  return { code: null, message: null, retryAfter: null };
}

// Texte à afficher pour une erreur : celui de la langue courante si le code est connu
// (clé `auth.error.<code>`), sinon le message du serveur, sinon `fallback`.
export function problemText(
  problem: ApiProblem,
  t: (key: string, vars?: Record<string, string | number>) => string,
  fallback: string,
): string {
  if (problem.code) {
    const key = `auth.error.${problem.code}`;
    const text = t(key, { seconds: problem.retryAfter ?? 0 });
    if (text !== key) return text;
  }
  return problem.message ?? fallback;
}

let unauthorizedListener: (() => void) | null = null;
let installed = false;

export function onUnauthorized(listener: (() => void) | null): void {
  unauthorizedListener = listener;
}

// À appeler une fois, au chargement du module d'authentification (avant le premier rendu : les
// effets des pages s'exécutent avant ceux de leur parent).
export function installAuthFetch(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    if (!url.startsWith(API_URL)) return original(input, init);
    const response = await original(input, { ...init, credentials: "include" });
    if (response.status === 401 && !url.startsWith(`${API_URL}/auth/`)) unauthorizedListener?.();
    return response;
  };
}
