# Dashboard d'historique des analyses

**Date** : 2026-09-22
**Statut** : Approuvé (design), implémentation à planifier

## Contexte

Le sprint DuckDB (`docs/superpowers/specs/2026-09-22-duckdb-analysis-storage-design.md`) a migré
le stockage des analyses vers une base interrogeable et exposé `GET /analyses` (filtres
`worker_label`/`poste_label`/`since`/`until`) et `GET /analyses/{id}`, mais avait explicitement
laissé de côté « l'UI d'historique/dashboard consommant `GET /analyses` ». Le sprint capsules
suivant l'a reconfirmé hors périmètre. Ce sprint construit cette UI : c'est le seul morceau du
roadmap qui manquait pour que tout ce que le backend sait déjà faire (lister, filtrer, consulter
une analyse passée) soit réellement utilisable.

**Recherche faite avant ce document** :

- `storage.list_analyses()`/`GET /analyses` retournent déjà exactement les champs nécessaires à
  une liste (id, date, côté, charge, salarié, poste, compteurs de frames, scores, répartition par
  niveau d'action), triés `created_at DESC`, sans pagination (pas nécessaire à l'échelle actuelle
  d'un déploiement mono-entreprise).
- `storage.get_analysis()`/`GET /analyses/{id}` retourne un objet dont les champs
  (`frame_count`, `detected_frame_count`, `max_score`, `average_score`, `time_by_action_level`)
  correspondent exactement au type `AnalysisSummary` déjà utilisé côté frontend pour le résultat
  d'une analyse fraîche — aucune divergence de forme à absorber.
- Les URLs vidéo/CSV/pose3D/recommandation ne sont jamais retournées par ces deux endpoints (elles
  ne le sont que par `POST /analyses`/`POST /uploads/{id}/complete`), mais suivent un pattern fixe
  et déjà utilisé partout ailleurs dans le code : `/analyses/{id}/video`,
  `/analyses/{id}/frames.csv`, `/analyses/{id}/pose3d`, `/analyses/{id}/recommendation`. Le
  frontend peut donc les reconstruire lui-même à partir du seul `analysis_id`, sans aucun
  changement d'API.
- `web/app/page.tsx` n'a pas de routing aujourd'hui (une seule page, 477 lignes) : le bloc
  "Résultat" (vidéo annotée, avatar 3D, résumé, lien CSV, recommandation) y est câblé en dur autour
  de l'état `result` d'une analyse tout juste terminée.
- La palette de couleurs par niveau d'action RULA existe déjà côté frontend
  (`ACTION_LEVEL_COLORS` dans `PostureAvatar3D.tsx`, même palette que `overlay.py::_COLOR_BY_LEVEL`
  côté Python) et les seuils exacts par score (`action_level()`, `rula/scoring.py` : ≤2 vert, ≤4
  jaune, ≤6 orange, >6 rouge).

## Décisions de cadrage

- **Aucun changement backend.** `GET /analyses` et `GET /analyses/{id}` couvrent déjà tout le
  besoin ; ce sprint est 100% frontend.
- **Deux nouvelles routes Next.js dédiées**, pas un onglet sur la page existante :
  `web/app/historique/page.tsx` (liste) et `web/app/historique/[id]/page.tsx` (détail d'une
  analyse). URLs partageables/marque-pageables, bouton retour navigateur naturel, et ça évite de
  faire encore grossir `page.tsx`.
- **La vue détail réutilise le rendu complet existant**, pas un résumé allégé : vidéo annotée,
  avatar 3D, résumé chiffré, lien CSV, bloc recommandation — exactement ce qu'affiche déjà
  `page.tsx` après une analyse fraîche. Ce bloc est extrait en composant partagé
  (`web/app/AnalysisResult.tsx`) plutôt que dupliqué, et réutilisé par les deux pages.
- **Tous les filtres déjà supportés par le backend sont exposés** : salarié (texte), poste
  (texte), période (depuis/jusqu'à). Rien à ajouter côté API pour ça.
- **Pas de pagination dans ce premier jet** — le dataset réel (analyses persistées en DuckDB
  depuis ce sprint, pas les runs `outputs/` d'avant, jamais migrés) reste petit à l'échelle d'un
  pilote mono-entreprise. À revisiter si le besoin se confirme.
- **Pas de tests unitaires sur l'orchestration des nouvelles pages**, cohérent avec le précédent
  déjà établi (`page.tsx`/`PostureAvatar3D.tsx` ne sont pas non plus unit-testés — seuls les
  modules purs le sont). Vérification manuelle via Playwright, comme chaque tranche frontend
  précédente.

## Architecture

### `web/app/AnalysisResult.tsx` (nouveau, extrait de `page.tsx`)

Composant partagé, props :

```ts
type AnalysisResultProps = {
  analysisId: string;
  side: Side;
  summary: AnalysisSummary;
  videoUrl: string;   // ex. `${API_URL}/analyses/{id}/video`
  csvUrl: string;
  pose3dUrl: string;
};
```

Contenu byte-pour-byte identique au bloc `{result && (...)}` actuel de `page.tsx` : `<video>`,
`<PostureAvatar3D>`, `<dl>` de résumé, lien CSV, bloc recommandation. Le fetch de la
recommandation (`GET /analyses/{id}/recommendation`, pattern `useEffect` avec flag `cancelled`,
déjà en place) déménage dans ce composant, gardé au même endroit conceptuel (déclenché par
`analysisId`).

`page.tsx` : le bloc `{result && (...)}` est remplacé par
`<AnalysisResult analysisId={result.analysis_id} side={result.side} summary={result.summary} videoUrl={...} csvUrl={...} pose3dUrl={...} />`.
Comportement inchangé, code partagé.

### `web/app/historique/page.tsx` (nouveau)

Client component. État : `analyses: AnalysisListItem[] | null` (`null` = chargement), `error`,
filtres (`workerLabel`, `posteLabel`, `since`, `until`, tous des `string` de champs contrôlés).

- Au montage et à chaque changement de filtre : construit l'URL `GET /analyses` avec les
  paramètres non vides (`workerLabel`→`worker_label`, etc.), `until` reçoit `T23:59:59` en
  suffixe avant l'envoi (le `<input type="date">` ne donne qu'une date, sans ça la borne
  supérieure exclurait la journée elle-même).
- Table : date formatée (`toLocaleString('fr-FR')`), salarié, poste, côté (« Droit »/« Gauche »),
  badge score max coloré (mêmes seuils/palette que `ACTION_LEVEL_COLORS`), score moyen, lien
  `→ /historique/{id}`.
- États : chargement (« Chargement... »), erreur réseau (message + les filtres restent modifiables
  pour réessayer), liste vide (« Aucune analyse enregistrée. » si aucun filtre actif, « Aucune
  analyse ne correspond à ces filtres. » sinon).
- Lien « ← Nouvelle analyse » vers `/`.

### `web/app/historique/[id]/page.tsx` (nouveau)

Client component, lit `id` via `useParams()`. Au montage : `GET /analyses/{id}`.

- 404 → « Analyse introuvable. » + lien retour vers `/historique`.
- Succès → construit les 3 URLs de ressource à partir de `id` (pattern fixe, voir ci-dessus) et
  rend `<AnalysisResult analysisId={id} side={data.side} summary={{frame_count: data.frame_count, ...}} videoUrl={...} csvUrl={...} pose3dUrl={...} />`.
- Lien « ← Retour à l'historique » vers `/historique`.

### Navigation

`page.tsx` (accueil) : petit lien « Historique » ajouté à côté du titre, vers `/historique`.

## Gestion d'erreurs

- `analysis_id` inconnu sur `/historique/{id}` → 404 API traduit en message « Analyse introuvable »
  + lien retour, pas de crash de page.
- Échec réseau sur `GET /analyses` (liste) → message d'erreur inline, filtres restent utilisables
  pour relancer une requête (pas de bouton "Réessayer" dédié — changer n'importe quel filtre
  relance déjà le fetch).
- Aucun changement aux routes existantes (`/analyses/{id}/video`, etc.) : leurs 404/206/416
  actuels sont déjà corrects et inchangés.

## Tests

- Aucun test automatisé nouveau (voir décision de cadrage ci-dessus) : le module ajouté
  (`AnalysisResult.tsx`) est une extraction de JSX existant, pas de nouvelle logique pure à tester
  unitairement ; les deux pages sont de l'orchestration fetch+rendu, comme `page.tsx` aujourd'hui.
- Vérification manuelle (Playwright, navigateur réel, deux serveurs) : liste se charge et affiche
  les analyses existantes ; chaque filtre (salarié, poste, depuis, jusqu'à) restreint bien les
  résultats ; clic sur une ligne ouvre `/historique/{id}` avec vidéo + avatar 3D + résumé +
  recommandation identiques à ce qu'affichait la page d'accueil pour cette même analyse au moment
  où elle a été produite ; navigation retour fonctionne des deux côtés ; id inconnu affiche le
  message 404 sans crash ; `tsc --noEmit`/`eslint`/`next build` propres.

## Hors périmètre de ce sprint

- Pagination de la liste (dataset trop petit pour être nécessaire aujourd'hui).
- Tri/colonnes personnalisables (tri fixe par date décroissante, comme le backend le fait déjà).
- Suppression d'une analyse depuis le dashboard (rétention/suppression reste un gap RGPD distinct,
  déjà documenté au README §8, non traité par ce sprint).
- Export groupé (CSV de plusieurs analyses, rapport agrégé HSE/RH) — mentionné en Phase 3 du
  README, pas ce sprint.
- Changement de l'API (`GET /analyses`/`GET /analyses/{id}` restent inchangés).
