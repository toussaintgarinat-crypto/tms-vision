export type NavItem = { href: string; label: string };

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Analyse" },
  { href: "/historique", label: "Historique" },
  { href: "/bilans", label: "Bilans de poste" },
  { href: "/bibliotheque", label: "Bibliothèque d'exercices" },
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
