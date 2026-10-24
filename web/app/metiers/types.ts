import { BilanTask } from "../bilans/types";

// Fiche type d'un modèle de métier : les mêmes champs qu'une fiche de bilan, sans identifiant.
export type MetierTask = Pick<BilanTask, "name" | "zones" | "activity_hours"> &
  Partial<
    Pick<BilanTask, "workstation" | "breaks" | "notes" | "load_kg" | "static_seconds">
  > & { cycles_per_minute?: number };

export type MetierModel = {
  id: string;
  title: string;
  description: string;
  origin: "library" | "custom";
  status: "draft" | "validated";
  source: "human" | "ai";
  validated_by: string | null;
  workday_hours: number;
  tasks: MetierTask[];
};
