# Plateforme de Vision par Ordinateur pour la Prévention des TMS et l'Ergonomie au Travail

## 1. Synthèse Exécutive

Le projet vise à associer la Vision par Ordinateur (Computer Vision) et l'expertise biomécanique d'un ostéopathe pour créer une solution globale d'analyse ergonomique, de prévention des Troubles Musculo-Squelettiques (TMS) et d'optimisation de la gestuelle au travail.

L'objectif est d'abandonner les formations théoriques génériques au profit d'un diagnostic sur-mesure hyper-personnalisé :

1. Filmer le salarié pendant un cycle de travail court (30 secondes à 3 minutes).
2. Analyser automatiquement les contraintes articulaires et les répétitions à risque à l'aide d'IA Open Source.
3. Prescrire des programmes de correction gestuelle et des micro-pauses guidées par des capsules vidéo d'étirements adaptées.

## 2. Analyse Métier & Cas d'Usage

### A. Analyse du poste & Diagnostic (1 à 3 minutes de vidéo)

Il n'est pas nécessaire d'enregistrer des heures de rush. Une séquence représentative d'un cycle métier suffit pour extraire les données fondamentales.

- **Logistique & Manutention** : Port de charges, flexions du tronc, torsions, répétitivité.
- **Industrie & Assemblage** : Postures statiques, bras en élévation, travail au-dessus des épaules.
- **Tertiaire / Bureau** : Position de la tête/cervicales, flexion des poignets, hauteur du buste.

### B. Parcours Utilisateur & Boucle Amélioration

```
┌────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────────────┐
│ 1. Capture Vidéo       │ ───> │ 2. Moteur IA             │ ───> │ 3. Bilan Ostéopathique   │
│ Smartphone / Caméra    │      │ Pose Estimation & Angles │      │ Diagnostic & Score RULA  │
└────────────────────────┘      └──────────────────────────┘      └──────────────────────────┘
                                                                               │
                                                                               ▼
┌────────────────────────┐      ┌──────────────────────────┐      ┌──────────────────────────┐
│ 6. Suivi RH / HSE      │ <─── │ 5. Application Salarié   │ <─── │ 4. Prescriptions         │
│ Tableau de bord global │      │ Micro-pauses & Capsules  │      │ Exercices & Étirements   │
└────────────────────────┘      └──────────────────────────┘      └──────────────────────────┘
```

## 3. Architecture Technique & Choix des Technologies

L'architecture repose à 100 % sur des briques Open Source, permettant une indépendance totale vis-à-vis des abonnements SaaS (comme Roboflow ou les API multimodales payantes) et garantissant la protection des données salariales.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           FRONT-END / CAPTURE                           │
│       Caméra Smartphone / Tablette / Flux RTSP (Vidéo MP4/MOV)          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      PIPELINE DE TRAITEMENT (PYTHON)                    │
│  1. Anonymisation : Détection & Floutage de visage (OpenCV / MediaPipe) │
│  2. Pose Estimation : MediaPipe Pose / MMPose (Squelette 33 keypoints)  │
│  3. Moteur Calculateur : Calcul vectoriel d'angles articulaires         │
│  4. Modèle Ergonomique : Implémentation des règles RULA / REBA          │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          REST API & DASHBOARD                           │
│  Backend FastAPI (Python) + Database SQLite/PostgreSQL                  │
│  Interface Web : React / Next.js (Visualisation & Recommandations)       │
└─────────────────────────────────────────────────────────────────────────┘
```

## 4. Benchmark des Technologies : Open Source vs Propriétaire

| Brique Fonctionnelle | Solution Propriétaire (ex: Post LinkedIn) | Alternative Open Source Recommandée | Licence OS | Coût Unitaire |
|---|---|---|---|---|
| Gestion / Annotation | Roboflow (SaaS) | CVAT / Label Studio | Apache 2.0 | 0 € |
| Auto-Labeling | API Astra 6 / GPT-Vision | Florence-2 / Qwen2-VL | Apache 2.0 | 0 € |
| Détection / Posture | RF-DETR | MediaPipe Pose / MMPose | Apache 2.0 | 0 € |
| Analyse & Visuel | Python + OpenCV | Python + OpenCV + SciPy | BSD | 0 € |
| Stockage & Serveur | Cloud Propriétaire AWS/GCP | Auto-hébergement (On-Premise / Proxmox) | N/A | Variable (Matériel) |

## 5. Spécifications du Moteur Ergonomique (RULA / REBA)

Le script Python lit les coordonnées (x, y, z) générées par le modèle de Pose Estimation pour calculer les angles biomécaniques réels frame par frame :

- **Angle Cervical** : Flexion/Extension de la tête par rapport à la verticale du buste.
- **Angle Épaule-Coude** : Élévation du bras par rapport à l'axe du corps (seuil critique à 45°).
- **Angle Lombaire** : Flexion du dos lors du ramassage ou du travail sur poste.

### Matrice de Scoring (Exemple RULA)

- **Vert (Score 1-2)** : Posture acceptable, aucun risque immédiat.
- **Jaune (Score 3-4)** : Investigation nécessaire, modifications à prévoir.
- **Orange (Score 5-6)** : Modification du poste à court terme.
- **Rouge (Score 7+)** : Risque élevé de TMS, intervention immédiate requise.

## 6. La Brique "Micro-Pauses & Capsules Vidéo"

Cette brique constitue l'outil de remédiation quotidienne de l'application.

### Médiathèque de l'Ostéopathe

- Bibliothèque de 30 à 45 vidéos courtes (30 à 60 secondes).
- Exercices catégorisés par zone anatomique (Rachis cervical, Lombaires, Épaules, Poignets/Mains, Hanches).

### Déclenchement Intelligent

Une fois la vidéo de poste analysée, le système associe les scores d'angles critiques aux capsules d'étirement correspondantes.

### Module Salarié (Web App / Mobile)

- Notification / Rappel de micro-pause.
- Lancement de la capsule vidéo guidée (ex: "3 étirements pour décompresser les cervicales après 2 heures sur écran").
- Optionnel : Vérification en temps réel via la webcam que l'exercice d'étirement est correctement exécuté.

## 7. Conformité RGPD & Sécurité des Données

L'analyse de l'image des salariés en entreprise est fortement encadrée par la CNIL et le RGPD.

- **Anonymisation à la source** : Le visage du salarié est flouté dès la première étape du traitement vidéo via un module OpenCV local, avant toute sauvegarde ou analyse d'angles.
- **Traitement On-Premise / Edge** : L'analyse vidéo s'exécute en local ou sur un serveur interne à l'entreprise. Aucune vidéo brute ne fuite vers des services Cloud tiers.
- **Droits des salariés** : Consentement préalable et droit d'accès au bilan individuel.

## 8. Feuille de Route de Déploiement (Roadmap MVP)

### Phase 1 : Prototypage & Validation PoC (Semaines 1 - 3)

- Développer le script Python de Pose Estimation avec MediaPipe Pose.
- Programmer les fonctions mathématiques de calcul d'angles (RULA simple).
- Tester le traitement sur 5 vidéos d'exemples (bureau, manutention, sport).

### Phase 2 : Création des Contenus & Interface (Semaines 4 - 6)

- Tournage de la bibliothèque de micro-pauses vidéo par l'ostéopathe.
- Création de l'interface d'import vidéo et d'affichage des scores/recommandations.
- Module de floutage automatique des visages.

### Phase 3 : Tiers Test & Pilote Entreprise (Semaines 7 - 10)

- Déploiement d'un projet pilote dans une entreprise partenaire ou un atelier.
- Ajustement des seuils de scoring ergonomiques avec l'ostéopathe.
- Génération des premiers rapports d'audit pour la direction HSE/RH.

## 9. Lancer le PoC (Phase 1)

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pytest                                    # suite de tests

PYTHONPATH=src venv/bin/python -m tms_vision.cli \
  --source chemin/vers/video.mp4 \
  --side right \
  --load-kg 2.5 \
  --wrist-twist normal \
  --output-dir outputs
```

`--source` accepte aussi `webcam` pour filmer en direct depuis une caméra branchée sur la
machine :

```bash
PYTHONPATH=src venv/bin/python -m tms_vision.cli --source webcam --side right --load-kg 0 --output-dir outputs
```

(interrompre avec Ctrl+C — la capture est actuellement lue en mémoire avant traitement, donc
mieux vaut limiter la prise à quelques dizaines de secondes ou enregistrer un fichier au
préalable si l'analyse doit couvrir un poste sur une durée plus longue).

**Conseil de prise de vue** : filmer la personne de profil pour des angles de flexion/extension
fiables (cou, tronc, bras).

Résultats dans `outputs/` : une vidéo annotée (squelette + badge de score RULA coloré), un CSV
détaillé par frame, et un résumé JSON (score max, score moyen, temps passé par niveau de risque).

**Note de vérification (Task 10)** : la suite de tests (64 tests) a été rejouée intégralement
avec succès. Le pipeline CLI complet a ensuite été exercé de bout en bout dans un environnement
sandboxé sans accès webcam physique, à l'aide d'une vidéo synthétique générée par OpenCV (un
cercle et un rectangle en mouvement sur fond uni, 40 frames à 10 fps) — cette vidéo ne contient
aucune silhouette humaine, donc MediaPipe n'y détecte aucune pose, ce qui est le comportement
attendu. Ce test a confirmé que les trois fichiers de sortie (vidéo annotée, CSV, JSON) sont
bien créés et correctement formés, avec une ligne par frame (`detected=False` sur les 40 lignes,
colonnes d'angles/scores vides) et un résumé JSON à `max_score: 0`, `average_score: 0`,
`time_by_action_level: {}` — conforme à la convention "aucune frame détectée" de la Task 8.
**Ce test ne remplace pas une vérification avec une vraie webcam ou une vidéo d'une personne
réelle** : avant de s'appuyer sur ce PoC pour une évaluation ergonomique réelle, l'utilisateur du
projet doit relancer la commande `--source webcam` (ou une vidéo filmant une personne) et
vérifier visuellement le squelette superposé et la cohérence des scores RULA obtenus.
