# Application de bureau (Windows et macOS)

Une installation « double-clic » pour le praticien : pas de Docker, pas de ligne de commande. Tout
tourne sur son ordinateur (l'API écoute sur 127.0.0.1 seulement) et les données y restent.

## Pour le praticien

**Windows** : télécharger `TMS-Vision-Setup.exe`, le lancer, puis ouvrir « TMS Vision » (bureau ou menu
Démarrer). Windows peut afficher « Windows a protégé votre ordinateur » (application non signée) :
*Informations complémentaires* puis *Exécuter quand même*.

**macOS** : télécharger le `.dmg` (Apple Silicon : M1 à M4 ; Intel pour les Mac plus anciens), glisser
« TMS Vision » dans Applications. Au premier lancement : clic droit sur l'application, *Ouvrir*, puis
*Ouvrir* (application non signée).

Une petite fenêtre « TMS Vision » s'ouvre et le navigateur affiche le site (adresse
`http://127.0.0.1:13000`). Pour arrêter : *Quitter* dans la petite fenêtre. Pour rouvrir le site :
*Ouvrir TMS Vision*. La caméra du navigateur fonctionne (adresse locale = connexion sécurisée).

**Données** (base, vidéos analysées, réglages), conservées lors des mises à jour et des
désinstallations ; le bouton *Dossier des données* y mène :
- Windows : `%APPDATA%\TMS Vision`
- macOS : `~/Library/Application Support/TMS Vision`

**Sauvegarde** : copier ce dossier. **Mise à jour** : installer la nouvelle version par-dessus.
**Journaux** (en cas de problème) : sous-dossier `logs` des données.

Pas de mot de passe : l'application n'est joignable que depuis l'ordinateur lui-même. Pas de vidéos
d'étirement pré-générées (outil `capsules`) : les exercices s'animent directement dans le navigateur.

## Construire les fichiers (côté développeur)

Les fichiers se fabriquent sur GitHub, sur de vrais Windows et macOS (on ne peut pas les construire
depuis Linux) : **Actions > Application de bureau > Run workflow**, ou en publiant une étiquette de
version (`git push origin v1.1.0`, voir `docs/VERSIONS.md`). Les fichiers sont dans *Artifacts* du
déroulé, et joints à la version GitHub pour une étiquette.

En local, sur la machine cible : `pip install -r requirements.txt -r deploy/desktop/requirements.txt`
puis `python deploy/desktop/build.py` (Python 3.11 et Node.js 20) ; le dossier est dans `dist/`.
Essai sans installateur depuis le dépôt : `python -m tms_vision.desktop --web-dir <site compilé>`.

## Fonctionnement

- `src/tms_vision/desktop.py` : lance l'API (dans le même processus, port 18000) et le site (Node.js
  embarqué, port 13000, mode Next.js « standalone »), ouvre le navigateur, petite fenêtre Tkinter.
- `deploy/desktop/build.py` + `tms-vision.spec` : construction du site (le port de l'API est figé dans
  le site), assemblage, PyInstaller. `installer.iss` : installateur Windows (Inno Setup).
- `src/tms_vision/paths.py` : retrouve `exercises/`, `metiers/`, `library/` et `VERSION`, dans le dépôt
  comme dans l'application construite.
- Vidéos annotées : OpenCV n'embarque pas toujours l'encodeur H.264 sous Windows et macOS ; avec
  `TMS_FFMPEG` (fourni par l'application), la vidéo est écrite puis réencodée en H.264 par ffmpeg.
