# Prochains sprints : comptes, validation et fiches

Mémo à lire en premier pour reprendre le chantier. Le plan complet (modèle de données, règles, décisions
ouvertes) est dans le document « TMS Vision : plan comptes, validation et fiches » :
https://claude.ai/artifact/T4P34ts66P3tp58TZmi19C
Les questions au juriste : « TMS Vision : questions pour le juriste » :
https://claude.ai/artifact/1qtDGLA2iw6XzaL9yh84yT

Objectif : chaque exercice proposé à un patient est relu et validé par un ostéopathe identifié, sur la fiche
entière (texte + animation 3D) ; les ostéopathes peuvent créer, copier et modifier des fiches.

## Où on en est

| Phase | Contenu | État |
|---|---|---|
| 0. Fondations | Interface en français et anglais, envoi d'emails SMTP | Livrée (2.0.0) |
| 1. Comptes | Comptes, connexion, rôles, journal, « Mon email », fin du mot de passe commun, application de bureau (compte, mot de passe oublié) | Livrée (2.0.0, correctif 2.0.1) |
| 2. Validation | Voir ci-dessous | **Construite (non publiée)** : tests au vert, reste à relire, puis publier (VERSION, CHANGELOG) |
| 3. Appropriation | Copier une fiche, la modifier, revalidation obligatoire, filiation affichée | À faire (dépend de la phase 2) |
| 4. Création de fiche | Formulaire + éditeur d'animation 3D manuel (curseurs d'angles, poses clés, aperçu) | À faire (dépend de la phase 3) |
| 5. Offre payante et assistant IA | Droits par offre, assistant, brouillon d'animation par IA | À définir avec Toussaint avant tout code |

## Phase 2 : Validation (construite)

Code : `src/tms_vision/validation.py`, routes `/exercises/{id}/validation|validate|withdraw-validation`,
`/osteopaths`, `PUT /bilans/{id}/osteo` ; écran `web/app/ValidationPanel.tsx` ; tests `tests/test_validation.py`.
Règle assouplie (décision de Toussaint) : l'animation peut être jouée en accéléré, jusqu'à 4x ; la vitesse
est enregistrée avec la validation. Décisions retenues : validation valable jusqu'à la prochaine modification de la fiche ; retrait possible
(nouvelle ligne) ; zone sans exercice validé : proposition « non validé ». Pas de réglage d'arrêt : les
bilans sans ostéopathe se comportent comme avant.

À construire :
- choix de l'ostéopathe sur le bilan (colonne `osteo_id`, vide = comportement actuel) ;
- tables `exercises`, `exercise_versions` (contenu figé + empreinte), `exercise_validations` (jamais modifiée
  ni supprimée ; un retrait est une nouvelle ligne) ;
- second chemin de chargement des exercices (fichiers `exercises/` puis base, la base l'emporte) sans casser
  `tests/test_exercises.py` ni `tests/test_library.py` ;
- écran de validation : animation et texte côte à côte, animation lancée en entier, case « j'ai vérifié le texte
  et l'animation de cette fiche » (la formule est enregistrée) ;
- filtre du programme d'un bilan sur l'ostéopathe choisi ; sans exercice validé pour une zone, proposer ceux de
  la bibliothèque marqués « non validé », avec un bouton « Valider » visible pour l'ostéopathe seulement ;
- étiquette « créé par … / validé par … le … » (ou « non validé ») sur la page patient et dans l'email ;
- seul un compte avec le rôle ostéopathe, connecté, peut valider (vérifié côté API, pas seulement dans le site) ;
- un test par règle de la section 5 du plan, dont les cas d'abus.

Les 173 fiches de Théo MARTIN ne sont pas validées automatiquement : il les valide lui-même depuis son compte,
après relecture de l'animation, une fois la phase 2 livrée.

### Garde-fou (levé sur instruction de Toussaint)

Toussaint a confirmé que l'accord de Théo MARTIN (qui sera un cabinet client) et celui du juriste sont
acquis : la phase 2 peut être publiée. Texte d'origine :

La phase 2 ne passe pas en production avant : (1) la réponse du juriste (sections 2, 3 et 6 de son document :
portée de la validation, statut de dispositif médical, durée de conservation du journal) et (2) l'accord de
Théo MARTIN. D'ici là : réglage éteint par défaut, et pas de version publiée qui l'active.

### Décision ouverte à trancher

Durée de validité d'une validation. Par défaut, si rien n'est décidé : valable jusqu'à la prochaine modification
de la fiche (recommandation du plan : illimitée au départ, à revoir selon le juriste).

## Phases suivantes, en bref

- **Phase 3** : copier = nouvel exercice, auteur d'origine conservé, jamais réécrit ; toute modification crée une
  version sans validation. Une fiche créée puis copiée par d'autres ne se supprime pas : elle est archivée.
- **Phase 4** : éditeur d'animation manuel d'abord ; limites du squelette signalées.
- **Phase 5** : l'assistant propose, la personne confirme ; il ne valide jamais une fiche et agit avec les droits
  du compte connecté. Attend les réponses du juriste sur les sections 4 et 10.

## Autres pistes, hors phases

- Autre langue après le français et l'anglais (ex. espagnol) : seulement avec un relecteur ostéopathe identifié ;
  l'animation est la même dans toutes les langues, seuls les textes se traduisent.
- Hébergement des pages patient pour les praticiens seuls sur l'application de bureau (leur lien pointe vers
  leur ordinateur et ne s'ouvre pas chez le patient) : chantier à part, rattaché à la phase 5.
- Tournage des micro-pauses vidéo par l'ostéopathe (30 à 45 vidéos), voir README, Phase 2.
- Calibrage des seuils RULA sur données réelles et jambes fixées à « soutenues », voir README, Phase 1.
