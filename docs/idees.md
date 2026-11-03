# Idées mises de côté

Pistes discutées, pas planifiées. Rien ici n'est développé.

## 1. Suivi continu des salariés

Filmer un salarié pendant toute sa journée (au lieu d'un cycle de 30 s à 3 min) pour mesurer ses
durées réelles par zone du corps, repérer les gestes répétés, les asymétries et la fatigue de fin de
journée, puis proposer des exercices au bon moment.

Apports : durées mesurées au lieu d'estimées, jours atypiques, évolution dans la journée, suivi
avant/après les exercices.

Technique : traitement en local (boîtier ou PC près du poste), seulement les angles du squelette
conservés (jamais l'image), agrégation par minute ou par heure, gestion des occlusions et de
plusieurs personnes dans le champ.

Cadre légal (France) : RGPD et CNIL, information et consultation du CSE, finalité précise
(prévention des TMS, jamais contrôle de la performance), analyse d'impact (AIPD) quasi certaine.

Garde-fous à prévoir dès la conception :
1. salarié volontaire, arrêt possible à tout moment ;
2. aucune vidéo stockée, seulement des angles ;
3. données individuelles réservées au salarié et au praticien, l'employeur ne voit que des
   statistiques de poste ou d'équipe, sans nom ;
4. aucune utilisation pour évaluer la performance.

Première étape réaliste : un pilote sur quelques postes avec des volontaires, en gardant le bilan
court actuel comme point de départ.

## 2. Mesure de l'usure des robots

Quand des robots remplaceront des postes, les filmer toute la journée pour comprendre l'usage de
leurs pièces : quelles articulations travaillent, à quels angles, à quelle fréquence, avec quelle
charge. Aucun enjeu de consentement ni de RGPD.

Apports : estimation de l'usure par pièce et maintenance prédictive, amélioration de la conception
d'après l'usage réel, comparaison de deux versions de robot ou de deux façons d'exécuter une tâche.

Réutilisation du projet : le moteur de calcul (angles, durées, cycles par minute, cumul par zone)
sert tel quel ; seul le corps change.

À ajouter : un modèle de squelette propre à chaque robot, des seuils d'usure fournis par le
constructeur (à la place des seuils RULA), et si le robot fournit ses propres capteurs (angles
moteurs, couples), la vidéo sert de contrôle plutôt que de source unique.

## 3. Usure des robots par les données du robot lui-même

Variante du §2 : au lieu de filmer le robot, un petit logiciel de collecte récupère ses mouvements
et ses mesures (angles des articulations, vitesses, couples ou courants moteurs, températures,
cycles) pour en déduire l'usure de chaque pièce. La vidéo du §2 reste possible comme autre source,
par exemple pour un robot fermé ou pour contrôler les mesures.

Apports par rapport à la vidéo : mesures directes et à haute fréquence, charge réelle sur chaque
articulation (invisible à l'image), fonctionnement continu, aucune caméra à installer.

Principe : **aucune marque visée au départ, le but est de s'adapter à un maximum de supports.** Le
moteur de calcul ne connaît qu'un format commun, et chaque robot ou machine se branche par un petit
adaptateur :

1. **Format commun** : une série de mesures horodatées par articulation ou par axe (position, vitesse,
   couple, température), avec un identifiant de robot et un modèle de robot décrivant ses
   articulations. C'est le même rôle que le squelette pour le corps humain.
2. **Adaptateurs interchangeables**, du plus universel au plus spécifique :
   - fichier journal exporté par le robot (CSV, JSON), importé à la main ou déposé dans un dossier :
     fonctionne avec presque tout, à faire en premier ;
   - protocoles ouverts de l'industrie (OPC UA, MQTT, Modbus, ROS) ;
   - interfaces propres à un constructeur, seulement à la demande d'un client ;
   - vidéo (§2), qui produit le même format commun.
3. **Description de chaque robot par un fichier** (articulations, limites, seuils d'usure du
   constructeur ou de l'exploitant), sur le modèle du dossier `metiers/` : ajouter un robot ne demande
   pas de programmer.
4. **Calculs** : cumul par articulation (angle parcouru, inversions de sens, charge × durée), cycles,
   passages près des limites, dérives dans le temps. Une évolution anormale signale une usure
   avant la panne.

Réutilisation du projet : cumuls par zone, cycles par minute, durées, bilans, tableaux de bord et
historique ; seuils RULA remplacés par les seuils d'usure.

Points d'attention : accès au contrôleur (souvent fermé ou sous garantie), sécurité (collecte en
lecture seule, jamais de commande envoyée au robot), volume de données (agréger par minute ou par
heure, garder le détail seulement autour des événements), calibration des seuils avec un
exploitant réel avant de promettre une durée de vie.

Première étape réaliste : l'import d'un fichier journal dans le format commun, un modèle de robot
décrit par fichier, et le cumul d'usure par articulation sur un cas réel fourni par un client.
