# Protocole de calibration des seuils avec l'ostéopathe

Ce document n'existait pas : aucune calibration n'a encore été faite, pour aucune zone. Il couvre les
six zones mesurées (cou, tronc, bras, avant-bras, main, pied) et les deux fichiers de seuils.

## 1. Ce qui est calibré, et ce qui ne l'est pas

| Fichier | Paramètres | Statut |
|---|---|---|
| `src/tms_vision/recurrence_thresholds.json` | par zone : amplitude minimale d'un mouvement (`min_prominence_deg`), variation tolérée pour une posture « statique » (`static_variation_deg`), cycles par minute au-delà desquels la zone est dite répétitive (`repetitive_cycles_per_minute`), durée statique à risque (`static_seconds`) | amplitude et variation : valeurs du PoC (10° / 15°) ; les deux autres : vides |
| `src/tms_vision/extremity_thresholds.json` | main : bornes de flexion des doigts (`finger_curl_bounds_deg`) ; pied : bornes de la cheville (`ankle_bounds_deg`) ; pour les deux, les coupures de niveau (`level_cutoffs`) | valeurs de départ, non validées |

Ne sont **pas** concernés : les bornes d'angle RULA (cou, tronc, bras, avant-bras, poignet), qui sont
celles de la méthode publiée, et les niveaux d'action RULA.

Tant que `"calibrated": false`, le rapport affiche « seuils non calibrés » et ne classe aucune zone
comme répétitive.

## 2. Ce que l'on cherche à établir

Pour chaque zone, trois réponses de l'ostéopathe, exprimées en chiffres :

1. **Amplitude** : à partir de quel déplacement angulaire un mouvement compte-t-il comme un cycle ?
2. **Immobilité** : en dessous de quelle variation une posture est-elle « tenue » (statique) ?
3. **Répétitivité** : combien de cycles par minute rendent une zone répétitive, et depuis quelle durée
   une posture tenue devient-elle à risque ?

Pour la main et le pied, en plus :

4. **Quelle flexion des doigts, quel écart de cheville** correspondent à une note 2 (à surveiller) et à
   une note 3 (à corriger) ?
5. **À partir de quelle note** une image compte comme « posture à risque » (coupures de niveau).

Chaque réponse doit venir de la pratique de l'ostéopathe ou d'une référence qu'il cite : le projet ne
choisit pas ces valeurs à sa place.

## 3. Matériel

- Un volontaire (pas un salarié du pilote tant que le consentement et l'information ne sont pas en
  place) qui accepte d'être filmé ; le visage est flouté dans la vidéo annotée mais **pas** dans le
  fichier d'origine : le supprimer après l'essai.
- Un téléphone ou une caméra fixe sur trépied, tournée à 1080p, 30 images par seconde, en vue de
  **profil strict** du côté analysé (le côté analysé est celui choisi à l'envoi), personne entière dans
  le champ, pieds compris, bon éclairage, vêtements non amples.
- Un goniomètre (ou, à défaut, une application d'angle sur photo) pour vérifier les angles tenus.
- Un chronomètre ou une application de métronome pour imposer les cadences.
- La fiche de relevé de la section 7.

## 4. Mise en place de chaque essai

1. Filmer 3 secondes de posture neutre debout avant chaque série (sert de repère).
2. Annoncer à voix haute le geste et la cadence au début (la voix n'est pas analysée : la vidéo
   annotée n'a pas d'audio).
3. Envoyer la vidéo par l'interface, côté analysé = côté filmé, poids = aucun.
4. Noter l'identifiant de l'analyse et télécharger le CSV de ses images (route
   `GET /analyses/{id}/frames.csv`, lien « CSV » de la page d'analyse).

## 5. Essais à réaliser

Un essai par ligne. Chaque série dure au moins 90 secondes pour les cadences (60 secondes
minimum pour les postures tenues). Refaire un essai dont la vidéo n'est pas exploitable (personne
coupée, pose non détectée sur plus de 10 % des images).

### 5.1 Amplitude et cadence (par zone)

Pour chaque zone, faire le geste suivant à trois cadences (6, 12 et 24 cycles par minute) et à deux
amplitudes (environ la moitié et la totalité de l'amplitude confortable) : six essais par zone.

| Zone | Geste |
|---|---|
| Cou | flexion-extension de la tête |
| Tronc | flexion avant puis retour |
| Bras | élévation antérieure de l'épaule, coude tendu |
| Avant-bras | flexion-extension du coude |
| Main | flexion-extension du poignet, doigts relâchés |
| Pied | pointe relevée puis tendue, talon posé (assis, jambe libre, pied visible) |

Le programme compte les cycles ; on compare avec le nombre réellement fait (compté à la vidéo). Le
seuil d'amplitude minimale se règle pour que les petits tremblements de la pose ne comptent pas, et que
les vrais cycles de la moitié d'amplitude comptent.

### 5.2 Posture tenue (par zone)

Tenir 30, 60 et 120 secondes une posture notée par l'ostéopathe comme « contrainte », sans bouger
volontairement. Le seuil de variation statique se règle pour que la tenue ressorte comme une seule plage
statique, sans que de petits mouvements volontaires de 5° la cassent ni que 15° la prolongent.

### 5.3 Main : doigts

Trois prises tenues 60 secondes : main ouverte, prise légère (flexion des doigts d'environ 45°), poing
serré. L'ostéopathe dit laquelle correspond à la note 1, 2, 3. Les doigts ne sont mesurés que si
MediaPipe voit la main : filmer la main de profil, non masquée, à moins de 1,5 m.

### 5.4 Pied : cheville

Trois positions tenues 30 secondes, pied visible (talon et orteils) : cheville neutre (angle droit),
écart d'environ 15° (pointe relevée ou tendue), écart d'environ 30°. L'ostéopathe dit laquelle
correspond à la note 1, 2, 3. Vérifier que l'écart mesuré par le goniomètre est proche de celui calculé
(le programme donne `ankle_flexion_deg` dans le CSV).

### 5.5 Situations réelles de contrôle

Filmer deux vraies postes de travail (un assis, un debout) pendant 3 minutes chacun, et demander à
l'ostéopathe de désigner, **sans voir les résultats**, les zones qu'il juge à risque. On compare ensuite
avec les zones que le programme recommande. Cette étape ne règle pas de seuil : elle sert à vérifier
que les réglages obtenus en 5.1 à 5.4 donnent des recommandations que l'ostéopathe reconnaît.

## 6. Dépouillement

Pour chaque essai (colonnes du CSV d'images : `timestamp_seconds`, `neck_flexion_deg`,
`trunk_flexion_deg`, `upper_arm_flexion_deg`, `lower_arm_angle_deg`, `wrist_flexion_deg`,
`ankle_flexion_deg`, `finger_curl_deg`) :

1. Comparer à la main l'angle tenu mesuré au goniomètre et l'angle donné par le CSV. Un écart
   systématique de plus de 10° sur une zone signale un problème de prise de vue, pas de seuil : refaire
   l'essai avant de régler quoi que ce soit.
2. Compter les cycles faits et ceux comptés par le programme (champ `cycles` du rapport de récurrence
   d'un bilan contenant l'analyse).
3. Régler `min_prominence_deg` : la plus grande valeur qui compte tous les vrais cycles de demi-amplitude.
4. Régler `static_variation_deg` : la plus petite valeur qui fait de chaque tenue une seule plage
   statique.
5. Fixer `repetitive_cycles_per_minute` et `static_seconds` **à partir de ce que dit l'ostéopathe**,
   pas à partir des mesures. Les mesures servent seulement à vérifier que le seuil choisi est atteignable
   avec ce que le programme sait compter.
6. Main et pied : placer les bornes entre les valeurs mesurées des trois prises (ou positions) de
   la section 5.3 et 5.4, de façon que la prise jugée « 2 » tombe entre les deux bornes. Régler
   `level_cutoffs` selon la note à partir de laquelle l'ostéopathe veut déclencher une recommandation.

## 7. Fiche de relevé (une ligne par essai)

| Date | Volontaire | Zone | Geste ou posture | Cadence ou durée visée | Angle tenu (goniomètre) | ID analyse | Cycles faits | Cycles comptés | Angle CSV | Note de l'ostéopathe (1/2/3) | Remarques |
|---|---|---|---|---|---|---|---|---|---|---|---|
| | | | | | | | | | | | |

## 8. Appliquer les valeurs

1. Reporter les seuils dans les deux fichiers JSON (une zone à la fois).
2. Lancer les tests : `pytest tests/test_recurrence.py tests/test_extremities.py`.
3. Passer `"calibrated"` à `true` **dans chaque fichier seulement quand toutes ses zones sont validées** :
   le drapeau est global au fichier, pas par zone.
4. Noter dans le README la date, le nom du validateur et les valeurs retenues. Les définitions
   d'exercices portent déjà `validated_by` et `validated_on` ; les seuils n'ont pas encore de champ
   équivalent (à ajouter dans les fichiers au moment de la validation).
5. Rejouer les deux situations réelles de 5.5.

## 9. Limites à garder en tête

- Les angles viennent d'une estimation de pose sur vidéo : une calibration faite avec une prise de vue
  donnée ne vaut que pour cette prise de vue (profil, trépied, distance de 2 à 3 m).
- Le poignet est mesuré en 2D, donc sensible à l'angle de prise de vue ; la cheville en 3D, les doigts
  seulement quand la main est vue.
- Un seul volontaire ne suffit pas à fixer un seuil : viser au moins trois personnes de morphologies
  différentes avant de passer `calibrated` à `true`.
- Les valeurs obtenues décrivent ce que l'outil sait mesurer, pas un diagnostic : elles ne remplacent pas
  l'évaluation de l'ostéopathe.
