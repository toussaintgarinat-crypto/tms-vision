# Fiche d'activité dans le bilan de poste — plan

Date : 2026-10-22. Statut : **plan validé dans son principe, rien n'est codé.** Destiné à une
nouvelle session : tout le contexte utile est ici.

## 1. Besoin exprimé (mots de l'utilisateur, résumés)

- Le serveur ne peut pas connaître le rythme réel d'une journée à partir d'une courte vidéo
  (échantillon de 30 s à 3 min). L'opérateur doit pouvoir **saisir lui-même** les horaires et les
  répétitions.
- Deux usages : **le patient** donne la vidéo et remplit un formulaire ; **le corps médical** remplit
  le formulaire.
- Un poste comporte **plusieurs tâches différentes** : il faut pouvoir les ajouter puis les
  **cumuler** pour que le logiciel prenne en compte toutes les tâches du poste.
- Public visé : professionnel de santé (ostéopathe) ; interface et textes en français.

## 2. Ce qui existe déjà (à réutiliser, pas à refaire)

Un **bilan de poste** regroupe des analyses vidéo ; le cumul par zone sur la journée existe.

| Élément | Où |
|---|---|
| Tables `bilans`, `bilan_analyses` (analyse + `activity_hours` + `representative`) | `src/tms_vision/storage.py` (`CREATE_BILANS_TABLE`, `CREATE_BILAN_ANALYSES_TABLE`, `_connect`, `create_bilan`, `attach_analysis`, `get_bilan`) |
| Routes `POST/GET /bilans`, `GET /bilans/{id}`, `POST /bilans/{id}/analyses`, `GET /bilans/{id}/recurrence`, `GET /bilans/{id}/program` | `src/tms_vision/api.py` (autour des lignes 480-570, `_build_bilan_report`) |
| Mesure des cycles par zone sur une vidéo (`cycles`, `cycles_per_minute`, `mean_cycle_seconds`, `longest_static_seconds`, `elevated_seconds`, `assessment`) | `src/tms_vision/recurrence.py` (`compute_recurrence`) |
| Projection sur la journée, refus si les activités dépassent la journée, part non documentée | `src/tms_vision/bilan.py` (`project_bilan`) |
| Seuils de détection par zone, livrés « non calibrés » | `src/tms_vision/recurrence_thresholds.json` |
| Programme d'étirements classé par heures projetées | `src/tms_vision/program.py` (`build_bilan_program`) |
| Pages web | `web/app/bilans/page.tsx`, `web/app/bilans/[id]/page.tsx`, `RecurrenceReport.tsx`, `types.ts` (zones et libellés), `recurrenceFormat.ts` |
| Spec d'origine de la récurrence | `docs/superpowers/specs/2026-10-21-recurrence-programme-etirements-design.md` |

Zones mesurées : `neck`, `trunk`, `upper_arm`, `lower_arm`, `hand`, `foot` (`capsules.ZONES`).

## 3. Ce qui manque (constaté dans le code)

- Une tâche n'existe que si elle vient d'une **analyse vidéo** : pas de tâche saisie à la main.
- Pas de **nom de tâche** : les analyses sont choisies dans une liste (date, poste, salarié).
- Pas de **plages horaires** : seulement une durée en heures.
- Les **répétitions ne sont jamais saisies**, uniquement mesurées.
- L'écran de résultat d'une analyse seule n'affiche pas la récurrence (elle n'existe que dans le
  rapport d'un bilan, `GET /analyses/{id}/recurrence` n'est pas consommée par l'interface).

## 4. Décisions déjà prises

1. **Fiche d'activité = une tâche du bilan**, avec ou sans vidéo. Le bilan reste l'unité de cumul.
2. **Ce qui est saisi est toujours affiché à côté de ce qui est mesuré**, avec son origine
   (« saisi par le praticien », « déclaré par le patient », « mesuré »). Jamais de mélange silencieux.
3. Pour la projection sur la journée, **la valeur saisie a priorité** sur la mesure de la même
   tâche et des mêmes zones.
4. Sans vidéo, la fiche donne une **projection de cycles et d'heures** mais **pas de score RULA**
   (il faut une posture mesurée) ni d'heures en niveau élevé : elles sont signalées « non mesurées ».
5. Ordre de réalisation : (1) fiche remplie par le soignant, (2) projection avec origine des valeurs,
   (3) lien patient (vidéo + formulaire). **Cette session ne traite que (1) et (2).**

## 5. Conception

### 5.1 Données

Nouvelle table `bilan_tasks` (créée avec `CREATE TABLE IF NOT EXISTS` dans `_connect`, comme les
autres ; `bilan_analyses` n'est **pas** modifiée) :

| Colonne | Type | Rôle |
|---|---|---|
| `id` | VARCHAR PK | identifiant (`generate_run_id()` de `pipeline.py`) |
| `bilan_id` | VARCHAR → `bilans(id)` | |
| `created_at` | TIMESTAMP | via `_to_naive_utc` |
| `name` | VARCHAR NOT NULL | « Peindre un plafond », « Saisie »… |
| `zones_json` | VARCHAR | zones concernées (sous-ensemble de `ZONES`) |
| `activity_hours` | DOUBLE | durée dans la journée (déduite des plages si elles sont données) |
| `time_slots_json` | VARCHAR NULL | `[{"start":"08:00","end":"12:00"}]` |
| `days_per_week` | DOUBLE NULL | information, non utilisée dans la projection journalière |
| `cycles_per_minute` | DOUBLE NULL | fréquence **canonique** ; l'interface convertit « par heure » ou « par jour » |
| `cycle_seconds` | DOUBLE NULL | durée d'un cycle |
| `static_seconds` | DOUBLE NULL | plus longue tenue statique |
| `load_kg` | DOUBLE NULL | information |
| `analysis_id` | VARCHAR NULL | analyse déjà rattachée au bilan que cette fiche complète |
| `source` | VARCHAR | `practitioner` aujourd'hui ; `patient` à l'étape 3 |
| `notes` | VARCHAR NULL | |

Règle d'association : si `analysis_id` est renseigné, la fiche **complète** la ligne vidéo du bilan
(les valeurs saisies remplacent la mesure pour les zones listées) ; sinon elle ajoute une entrée
autonome au cumul. Rejeter `analysis_id` absent de `bilan_analyses` pour ce bilan.

### 5.2 Calcul (`bilan.py`)

- `project_bilan(workday_hours, items, tasks=None)` : `tasks` est optionnel, pour ne casser ni les
  appels ni les tests existants.
- Pour une fiche autonome : `projected_cycles[zone] += cycles_per_minute * 60 * activity_hours` pour
  chaque zone listée ; `projected_elevated_hours` n'est pas alimenté et la zone reçoit un
  avertissement « non mesuré ».
- Pour une fiche liée à une vidéo : même formule, mais **à la place** de la valeur mesurée de cette
  analyse pour les zones listées ; la valeur mesurée reste dans la sortie (`measured`) à côté de
  `declared`.
- Les durées de toutes les entrées (vidéos incluses) restent soumises à la règle existante : le total
  ne dépasse pas la journée (`ValueError`, déjà transformée en erreur par l'API).
- Plages horaires qui se chevauchent entre tâches : **avertissement**, pas d'erreur.
- Sortie : chaque entrée porte `source` (`measured` / `practitioner` / `patient`) ; les totaux par
  zone gardent leurs clés actuelles pour ne pas casser `RecurrenceReport.tsx`.

### 5.3 API (`api.py`)

- `POST /bilans/{id}/tasks`, `PUT /bilans/{id}/tasks/{task_id}`, `DELETE /bilans/{id}/tasks/{task_id}`.
- `GET /bilans/{id}` renvoie aussi `tasks`.
- Validation Pydantic : nom non vide, zones connues, durées `> 0` et `<= 24`, `cycles_per_minute`
  `>= 0`, plages `HH:MM` avec fin > début. Messages d'erreur en français.

### 5.4 Interface (`web/app/bilans/[id]/page.tsx`)

- Section « Tâches du poste » : liste des tâches (vidéo et fiches) avec leur origine, puis un
  formulaire « Ajouter une tâche » : nom, zones (cases à cocher avec `ZONE_LABELS`), plages horaires
  ou durée, répétitions (champ + unité : par minute / par heure / par jour), durée d'un cycle, tenue
  statique, charge, notes, et « compléter une vidéo du bilan » (liste des analyses rattachées).
- Dans `RecurrenceReport.tsx` : badge d'origine par ligne, et « déclaré : X/min · mesuré : Y/min »
  quand les deux existent.
- Logique pure (conversion par heure/jour → par minute, total des plages, formatage) dans un fichier
  `*.ts` à part avec son `*.test.ts`, comme `recurrenceFormat.ts`.

## 6. Tests à écrire

- `tests/test_bilan.py` : projection avec fiche autonome, fiche qui complète une vidéo (la valeur
  saisie l'emporte, la mesure reste visible), dépassement de la journée, chevauchement (avertissement),
  fiche sans zone mesurable.
- `tests/test_storage.py` : création, lecture, modification, suppression, `analysis_id` hors bilan.
- `tests/test_api.py` : routes, validations, 404, 409/422.
- `web/app/bilans/*.test.ts` : conversions d'unités, total des plages.
- Vérification dans un navigateur : créer un bilan, ajouter deux tâches (une vidéo, une fiche),
  contrôler le cumul et les badges.

## 7. Hors périmètre de cette étape

- **Lien patient** (étape 3) : page à jeton, comme `/bibliotheque/envoi/<jeton>`, où le patient dépose sa
  vidéo et remplit la fiche (`source = patient`). Exige un texte de consentement (données de santé,
  RGPD) et, à terme, des comptes.
- **Authentification** : l'API est ouverte, comme le reste du projet.
- **Calibration des seuils** `recurrence_thresholds.json` : à faire avec l'ostéopathe.
- Prise en compte de `days_per_week` dans une projection hebdomadaire.

## 8. Questions encore ouvertes (à poser à l'utilisateur)

1. Champs de la fiche : manque-t-il une information que le soignant demande toujours (poste de
   travail, fréquence des pauses, côté dominant) ?
2. Une tâche saisie doit-elle pouvoir s'appliquer à **plusieurs zones avec des fréquences
   différentes** (par exemple cou 6/min et avant-bras 20/min) ? Le plan ci-dessus applique une seule
   fréquence à toutes les zones listées ; plus fin = une fréquence par zone.

## 9. Repères pour la nouvelle session

- Dépôt `toussaintgarinat-crypto/tms-vision`, branche `main` à jour (bibliothèque d'exercices, menu
  rétractable et correctif macOS de `./tms start` sont fusionnés : PR n°1 et n°2).
- Lancer : `./tms setup` puis `./tms start` (API 8000, site 3000). Tests : `./tms test`, ou
  `python -m pytest` et `cd web && npm test`, `npx eslint .`, `npx tsc --noEmit`.
- **Dans l'environnement cloud**, 31 tests Python échouent déjà avant toute modification
  (`mediapipe` sans module `solutions`) : `test_api.py` (11), `test_pipeline.py` (8),
  `test_pipeline_anonymization.py` (8), `test_cli.py` (2), `test_pose_estimation.py` (2). Ne pas les
  attribuer à un nouveau changement ; comparer avant/après.
- `web/AGENTS.md` : cette version de Next.js a des changements incompatibles, lire
  `web/node_modules/next/dist/docs/` avant d'écrire du code web. Les pages existantes sont des
  composants clients qui lisent les paramètres avec `useParams` : suivre ce motif.
- Arrêter les serveurs de test avec `fuser -k 3000/tcp 8000/tcp` (pas `pkill -f`, qui peut tuer le
  shell).
- Conventions du dépôt : commentaires et messages en français, `draft`/`validated` pour le contenu
  médical, un changement = une branche + pull request ; l'utilisateur doit dire explicitement
  d'ouvrir et de fusionner une pull request.
