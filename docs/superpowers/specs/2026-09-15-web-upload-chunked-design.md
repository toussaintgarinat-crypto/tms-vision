# Phase 2 (tranche 2) — Upload de fichier vidéo par chunks

**Date** : 2026-09-15
**Statut** : Approuvé

## Contexte

La tranche 1 de la Phase 2 (`docs/superpowers/specs/2026-09-14-web-capture-fastapi-design.md`)
a livré une page web qui enregistre un clip via la caméra du navigateur
(`getUserMedia`/`MediaRecorder`, plafonné 640×480/30s pour rester compatible avec le pipeline en
mémoire) puis l'envoie en un seul `POST /analyses` multipart.

Cette tranche ajoute un second chemin : importer un fichier vidéo déjà enregistré (sur
l'appareil de l'utilisateur), sans les contraintes de résolution/durée imposées à la capture
caméra live — utile par exemple pour analyser un clip filmé avec l'appareil photo natif du
téléphone plutôt que via le navigateur.

L'envoi se fait par chunks de 5 Mo plutôt qu'en une seule requête. **Motivation : rester sous les
limites de taille de requête** qui peuvent exister sur le chemin réseau (proxy, tunnel HTTPS type
Cloudflare — voir `.claude/skills/iphone-tunnel-test` — hébergeur futur), pas pour offrir une
reprise complète après fermeture du navigateur (hors périmètre, voir plus bas).

## Décisions de cadrage

- **Alternative à la caméra, pas un remplacement.** La page propose les deux : « Démarrer la
  caméra » ou « Importer une vidéo ». Les deux chemins convergent vers le même formulaire
  (côté/charge/torsion) et le même affichage de résultat — seule la façon d'obtenir le fichier à
  analyser diffère.
- **Chunks de 5 Mo, envoi séquentiel.** Compromis entre rester loin des limites de taille de
  requête courantes (Cloudflare Tunnel gratuit ~100 Mo, proxies génériques souvent 10-100 Mo) et
  un nombre de requêtes raisonnable. Séquentiel plutôt que parallèle : l'objectif est la fiabilité
  sous une limite de taille, pas la vitesse — un envoi parallèle complexifierait la reprise par
  chunk sans bénéfice pour ce besoin.
- **Retry par chunk, pas de reprise de session.** Chaque `PUT` de chunk est réessayé jusqu'à 3
  fois côté navigateur avant d'abandonner l'upload entier. Si l'onglet se ferme ou l'upload est
  abandonné, la session n'est pas récupérable — l'utilisateur relance depuis le début. Voir « Hors
  périmètre ».
- **État de session sur le système de fichiers, pas de dict en mémoire ni de DB.** La présence de
  `meta.json` + des fichiers `chunk_NNNNNN` dans le dossier de session constitue tout l'état.
  Cohérent avec le choix déjà acté (tranche 1) de ne pas introduire de DB dans cette phase, et
  survit à un redémarrage d'`uvicorn --reload` en cours d'upload (un dict en mémoire ne le
  supporterait pas).
- **Réutiliser `analyze_video()` sans modification.** Le réassemblage produit un seul fichier
  vidéo sur disque, traité exactement comme le fichier reçu par `/analyses` aujourd'hui — aucun
  changement au pipeline Phase 1.

## Approche

Le navigateur découpe le `File` sélectionné en tranches de 5 Mo (`File.slice()`) et les envoie
séquentiellement à trois nouveaux endpoints FastAPI qui les réassemblent sur disque avant de
déclencher l'analyse existante.

```
Navigateur                                    FastAPI
───────────                                   ───────
Fichier sélectionné (input type="file")
  │
  ├─ POST /uploads {filename, total_chunks}
  │     └─→ crée outputs/.uploads/{upload_id}/meta.json ──→ {upload_id}
  │
  ├─ pour i de 0 à total_chunks-1 (séquentiel, retry ×3 par chunk) :
  │     PUT /uploads/{upload_id}/chunks/{i}  (multipart, un chunk)
  │        └─→ écrit chunk_{i:06d} dans le dossier de session
  │
  └─ POST /uploads/{upload_id}/complete  {side, load_kg, wrist_twist}
        └─→ vérifie que chunk_000000..chunk_{N-1} existent tous
        └─→ concatène dans l'ordre → fichier temporaire unique
        └─→ analyze_video(...)  (identique à /analyses)
        └─→ supprime le dossier de session
        └─→ renvoie le même JSON que /analyses
```

## Structure du projet (ajouts sur l'existant)

```
TMS vision/
├── src/tms_vision/
│   └── api.py                       # MODIFIÉ — + POST /uploads, PUT /uploads/{id}/chunks/{i},
│                                     #   POST /uploads/{id}/complete
├── tests/
│   └── test_api.py                  # MODIFIÉ (ou nouveau test_upload_api.py) — couverture des
│                                     #   3 nouveaux endpoints
├── web/app/page.tsx                  # MODIFIÉ — bouton "Importer une vidéo", input file,
│                                     #   chunking + boucle d'envoi + barre de progression
└── outputs/.uploads/                 # NOUVEAU — dossiers de session éphémères (gitignored,
                                       #   comme outputs/ lui-même)
```

## Flux de données détaillé

1. L'utilisateur clique « Importer une vidéo », choisit un fichier via `<input type="file"
   accept="video/*">`. Le fichier remplace `recordedFile` dans l'état existant — le formulaire
   (côté/charge/torsion) et le bouton « Analyser » qui suivent sont donc partagés avec le chemin
   caméra, sans duplication.
2. Au clic sur « Analyser » (chemin upload uniquement) :
   a. `POST /uploads` avec `filename` (nom original, pour dériver l'extension) et `total_chunks`
      (calculé côté client : `Math.ceil(file.size / CHUNK_SIZE)`). L'API crée
      `outputs/.uploads/{uuid4().hex}/meta.json` contenant `{total_chunks, filename}` et renvoie
      `{"upload_id": ...}`.
   b. Pour chaque tranche `i` (0 à total_chunks-1), `file.slice(i * CHUNK_SIZE, (i+1) *
      CHUNK_SIZE)` puis `PUT /uploads/{upload_id}/chunks/{i}` (multipart, un seul champ `file`).
      En cas d'échec réseau, jusqu'à 2 nouvelles tentatives du même chunk avant d'abandonner tout
      l'upload et d'afficher une erreur. La barre de progression affiche `i+1 / total_chunks`.
   c. Une fois tous les chunks envoyés avec succès, `POST /uploads/{upload_id}/complete` avec les
      champs du formulaire (`side`, `load_kg`, `wrist_twist`).
3. Côté serveur, `complete` vérifie que `chunk_000000` à `chunk_{total_chunks-1:06d}` existent
   tous dans le dossier de session (422 sinon), les concatène dans l'ordre en un fichier
   temporaire (même logique de suffixe que `/analyses` aujourd'hui : extension dérivée de
   `meta.json["filename"]`, `.webm` par défaut), puis appelle `analyze_video(...)` exactement
   comme `/analyses` le fait. Le dossier de session est supprimé dans un `finally`, que l'analyse
   réussisse ou échoue.
4. La réponse JSON est strictement identique à celle de `/analyses` — la page affiche le résultat
   (vidéo annotée, score RULA, lien CSV) via le même bloc JSX que le chemin caméra.

## Endpoints (détail)

- **`POST /uploads`** — `filename: str = Form(...)`, `total_chunks: int = Form(..., ge=1)`.
  Crée le dossier de session, écrit `meta.json`. Renvoie `{"upload_id": str}`.
- **`PUT /uploads/{upload_id}/chunks/{index}`** — `file: UploadFile = File(...)`.
  - 404 si le dossier de session ou `meta.json` n'existe pas.
  - 400 si `index` hors de `[0, total_chunks)`.
  - Écrit le contenu dans `chunk_{index:06d}` (écrase si déjà présent — un retry client du même
    index est donc idempotent).
- **`POST /uploads/{upload_id}/complete`** — `side`, `load_kg`, `wrist_twist` (mêmes types/
  validations que `/analyses`).
  - 404 si le dossier de session ou `meta.json` n'existe pas.
  - 422 si un `chunk_{i:06d}` manque pour `i` dans `range(total_chunks)`.
  - Concatène, appelle `analyze_video`, nettoie, renvoie le JSON standard (identique à
    `/analyses`).

## Gestion d'erreurs

- Chunk PUT échoué après les tentatives client → upload entier abandonné, message clair affiché
  (« Envoi interrompu, réessayez l'import du fichier. ») ; pas de reprise partielle dans cette
  tranche.
- `complete` avec chunk manquant (session corrompue ou incomplète) → HTTP 422, message affiché.
- Vidéo réassemblée illisible par `cv2` → même traitement que `/analyses` aujourd'hui
  (`FileNotFoundError`/`RuntimeError` → 422).
- `upload_id` inconnu (session déjà nettoyée, ou erronée) → HTTP 404 sur `chunks`/`complete`.

## Tests

- Nouveaux tests dans `tests/test_api.py` (ou `tests/test_upload_api.py`) avec `TestClient` :
  - Chemin heureux : `POST /uploads` → plusieurs `PUT /uploads/{id}/chunks/{i}` → `POST
    .../complete` produit exactement le même corps de réponse qu'un `POST /analyses` équivalent
    sur la même vidéo synthétique.
  - `complete` avec un chunk manquant → 422.
  - `PUT chunks/{index}` avec `upload_id` inconnu → 404.
  - `PUT chunks/{index}` avec `index` hors bornes → 400.
  - Réassemblage correct même si les chunks sont envoyés dans un ordre différent de l'ordre
    d'index (le nom de fichier `chunk_{index:06d}` fait foi, pas l'ordre d'arrivée des requêtes).
- Pas de test end-to-end navigateur automatisé pour le chunking côté client dans cette tranche
  (pas d'infra de test frontend dans `web/` à ce jour) — vérification manuelle via
  Playwright/navigateur réel avant de considérer la tranche terminée, comme fait pour la tranche 1
  (voir `.superpowers/sdd/progress.md`).

## Hors périmètre (cette tranche)

- **Reprise après fermeture du navigateur ou perte totale de connexion.** Seul le retry par chunk
  en cours d'upload est géré ; une session abandonnée n'est pas récupérable.
- **Upload parallèle des chunks.** Séquentiel uniquement.
- **Nettoyage automatique des sessions abandonnées** dans `outputs/.uploads/`. Dette connue,
  cohérente avec la dette déjà documentée sur `outputs/` lui-même (pas de rétention/cleanup — voir
  `.superpowers/sdd/progress.md`).
- **Limite de taille totale de fichier côté serveur.** Aucune limite explicite n'est ajoutée au-delà
  de ce que le pipeline peut traiter — dette déjà documentée pour `/analyses`.
- **Authentification, déploiement.**
- Le chemin caméra existant (`/analyses`) n'est pas modifié.
