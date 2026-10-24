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
export const DOMAIN_LABELS: Record<MetierDomain, string> = {
  "terrain-btp": "Terrain et BTP",
  "industrie-logistique": "Industrie et logistique",
  "alimentaire-commerce": "Alimentaire et commerce",
  "sante-soins": "Santé et soins",
  "tertiaire-autres": "Tertiaire et autres",
};

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
