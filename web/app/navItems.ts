// `labelKey` : clé de traduction du libellé (voir i18n/messages).
export type NavItem = { href: string; labelKey: string };

export const NAV_ITEMS: NavItem[] = [
  { href: "/", labelKey: "nav.analysis" },
  { href: "/historique", labelKey: "nav.history" },
  { href: "/bilans", labelKey: "nav.bilans" },
  { href: "/bibliotheque", labelKey: "nav.exerciseLibrary" },
  { href: "/metiers", labelKey: "nav.jobLibrary" },
];

// Page de l'élément du menu en cours : « / » n'est actif que sur l'accueil, les autres aussi sur
// leurs sous-pages (/historique/abc reste dans « Historique »).
export function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

// Pages sans menu : la page de rendu des vidéos (ouverte par un navigateur sans interface, pixels
// comptés) et la page du patient, qui ne doit pas voir les outils du praticien.
export function isMenuHidden(pathname: string): boolean {
  return (
    pathname === "/render" ||
    pathname.startsWith("/render/") ||
    pathname.startsWith("/bibliotheque/envoi/")
  );
}
