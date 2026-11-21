import { BilanTask } from "../bilans/types";

// Fiche type d'un modèle de métier : les mêmes champs qu'une fiche de bilan, sans identifiant.
export type MetierTask = Pick<BilanTask, "name" | "zones" | "activity_hours"> &
  Partial<
    Pick<BilanTask, "workstation" | "breaks" | "notes" | "load_kg" | "static_seconds">
  > & { cycles_per_minute?: number };

export type MetierDomain =
  | "terrain-btp"
  | "industrie-logistique"
  | "alimentaire-commerce"
  | "sante-soins"
  | "tertiaire-autres";

// Ordre d'affichage des domaines d'activité dans la bibliothèque.
export const DOMAINS: MetierDomain[] = [
  "terrain-btp",
  "industrie-logistique",
  "alimentaire-commerce",
  "sante-soins",
  "tertiaire-autres",
];

// Clé de message du nom d'un domaine (à traduire avec `t`).
export function domainKey(domain: MetierDomain): string {
  return `metiers.domain.${domain}`;
}

export type MetierModel = {
  id: string;
  title: string;
  description: string;
  // Absent des modèles du praticien (origin "custom").
  domain?: MetierDomain;
  origin: "library" | "custom";
  status: "draft" | "validated";
  source: "human" | "ai";
  validated_by: string | null;
  workday_hours: number;
  tasks: MetierTask[];
};
