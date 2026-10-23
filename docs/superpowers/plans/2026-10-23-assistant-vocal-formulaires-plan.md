# Assistant vocal qui remplit les formulaires — plan

Date : 2026-10-23. Statut : **plan à valider, rien n'est codé.**

## 1. Besoin exprimé

- Un assistant IA dans TMS Vision qui **écoute la personne** et **remplit les informations** à sa place.
- S'inspirer de deux dépôts existants de l'auteur : **Workplace** (briques `transcription`, `voix`,
  assistant « Jarvis » à outils et confirmations) et **avocat-v2** (`AssistantPanel`, route
  `/api/assistant/chat`, registre de fournisseurs LLM, voix navigateur).
- **Optionnel : désactivé par défaut**, à activer par l'utilisateur.
- Écoute : **dictée du navigateur ET transcription souveraine**, au choix.
- Remplissage : **(1) pré-remplir puis valider** et **(2) dialogue guidé** (l'assistant pose les
  questions une à une).

## 2. Ce qu'on reprend des deux dépôts

| Besoin | Source | Adaptation pour TMS Vision |
|---|---|---|
| Dictée navigateur | avocat-v2 `AssistantPanel.tsx` (`SpeechRecognition`, fr-FR) ; Workplace `core/dashboard.html` | Hook React `useSpeech` |
| Transcription souveraine | Workplace `briques/transcription` : `POST /transcrire` (Whisper local, repli honnête `place_holder: true`) | L'API TMS appelle cette brique si `TMS_TRANSCRIPTION_URL` est défini ; sinon repli honnête |
| Client LLM compatible OpenAI, config par variables, clé jamais en clair | avocat-v2 `src/lib/llm/registry.ts`, route chat | `httpx` côté FastAPI (déjà dans `requirements.txt`) ; variables `TMS_ASSISTANT_LLM_URL/KEY/MODEL` ; un modèle local (Ollama) est possible |
| Garde-fou « jamais d'action sans confirmation » | Workplace S7, avocat-v2 `confirme=true` | L'assistant **ne sauvegarde jamais** : il remplit, l'utilisateur clique « Enregistrer » |
| Lecture à voix haute nettoyée | avocat-v2 `voix.ts` (`pourLaVoix`) | Questions du mode guidé lues via `speechSynthesis` (option) |
| Repli honnête (ne jamais inventer) | Workplace partout | Une information non dite reste vide ; aucun champ n'est deviné |

## 3. Architecture

```
Navigateur                                   API FastAPI (src/tms_vision/assistant.py)
┌───────────────────────────┐                ┌───────────────────────────────────────┐
│ Réglage « Assistant vocal »│  GET /assistant/config  → activé ? moteurs dispos ?    │
│ (case à cocher, off)       │                │                                       │
│ Micro ─ dictée navigateur ─┼─ texte ───────►│ POST /assistant/extract               │
│       └ ou audio ──────────┼─ /assistant/transcribe → brique transcription → texte │
│ Panneau assistant          │◄── champs + prochaine question ── LLM (JSON strict)   │
│ champs surlignés « IA »    │                │ + validation pydantic (mêmes règles    │
│ [Enregistrer] = utilisateur│                │   que BilanTaskBody)                  │
└───────────────────────────┘                └───────────────────────────────────────┘
```

### 3.1 API (nouveau module `src/tms_vision/assistant.py`)

- `GET /assistant/config` → `{enabled, llm_configured, transcription_configured}`. Désactivé tant que
  `TMS_ASSISTANT=on` n'est pas posé **et** que l'utilisateur n'a pas coché l'option dans l'interface.
- `POST /assistant/transcribe` (audio) → `{text, backend, placeholder}` ; relais vers la brique
  Workplace `transcription`. Sans moteur : `placeholder: true`, `text: ""` (jamais de faux texte).
- `POST /assistant/extract` `{form, transcript, current_values, history, mode}` → LLM en
  « sortie JSON stricte » selon le **schéma du formulaire** ; réponse
  `{fields, missing, next_question, warnings}`. Chaque champ est **revalidé côté serveur**
  (zones dans `ZONES`, plages horaires sans chevauchement, unités converties avec la même règle
  que `toCyclesPerMinute`). Un champ invalide est écarté avec un avertissement, pas appliqué.
- Les erreurs sont en français et sans détail technique (même style que `api.py`).

### 3.2 Interface (`web/app/assistant/`)

- `AssistantToggle` : option « Assistant vocal » **désactivée par défaut**, mémorisée dans
  `localStorage` (par navigateur, `try/catch`), réglage du moteur d'écoute (navigateur / souverain).
- `useSpeech` : deux implémentations derrière la même interface (`SpeechRecognition` ;
  `MediaRecorder` → `/assistant/transcribe`), avec repli honnête si le navigateur ne sait pas.
- `AssistantPanel` : micro, transcription en direct, mode **Dictée** (tout dire d'un coup →
  champs pré-remplis) ou **Guidé** (question affichée, lue à voix haute si l'option est cochée).
- `formSchemas.ts` : un schéma par formulaire (nom, libellé, type, choix possibles). Ajouter un
  formulaire = ajouter un schéma, comme « ajouter une brique » dans Workplace.
- `applyAssistantFields.ts` (logique pure, testée) : traduit la réponse en état du formulaire,
  **sans écraser** ce que l'utilisateur a déjà tapé sauf demande explicite ; marque les champs
  remplis par l'IA (surlignage) pour la relecture.

### 3.3 Formulaires couverts

1. **Fiche d'activité** (`web/app/bilans/TaskSection.tsx`) : nom, zones, plages horaires ou durée,
   répétitions + unité, durée de cycle, tenue statique, charge, jours/semaine, poste, pauses, notes.
   Exemple : « le matin de 8 h à 12 h il peint des plafonds, bras levés, environ 20 gestes par minute,
   pas de pause avant midi » → nom, plage 08:00–12:00, zones épaule et cou, 20/min, pause « Aucune ».
2. Création d'un bilan (nom, durée de journée) puis charge d'une analyse (`LoadEditor.tsx`) :
   étape suivante, même mécanisme.

## 4. Décisions à valider

1. **Confidentialité** : les propos d'un salarié concernent sa santé et son travail. Par défaut
   l'assistant est **éteint**, un bandeau dit où part le texte (navigateur/Google, LLM choisi), et un
   LLM **local** (Ollama) reste possible pour qu'aucune donnée ne sorte. Aucune donnée d'identité
   n'est envoyée au LLM au-delà du texte dicté.
2. **Fournisseur LLM** : une seule configuration par installation (variables d'environnement), comme
   le reste de TMS Vision ; pas de réglage par utilisateur en v1.
3. **Dépendance à Workplace** : la transcription souveraine suppose la brique Workplace
   `transcription` (ou tout service avec la même route `/transcrire`). Sans elle, seule la dictée
   navigateur fonctionne.

## 5. Ordre de réalisation

1. API : `assistant.py` (config, extraction avec faux LLM en test, validation) + tests pytest.
2. Logique pure web : schémas, `applyAssistantFields`, tests vitest.
3. Interface : réglage, dictée navigateur, panneau, branchement sur la fiche d'activité.
4. Mode guidé + lecture à voix haute.
5. Transcription souveraine (`MediaRecorder` + relais vers la brique).
6. Documentation : `docs/INSTALLATION-CLIENT.md` (variables), `.env.example`, `CHANGELOG.md`.

Vérification : `./tms test`, puis essai réel dans le navigateur (Playwright) avec un faux LLM puis
un vrai modèle ; la dictée vocale elle-même ne se teste pas en headless et sera signalée « à valider
à la main ».
