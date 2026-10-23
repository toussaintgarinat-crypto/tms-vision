#!/usr/bin/env bash
# Publie une nouvelle version : met à jour VERSION et CHANGELOG.md, crée le commit et l'étiquette Git.
#
#   deploy/release.sh 1.1.0
#
# Avant : écrire les nouveautés sous « ## [Non publié] » dans CHANGELOG.md, être sur la branche main,
# sans modification en cours. Le script ne pousse rien : il affiche la commande à lancer.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

NEW="${1:-}"
[[ "$NEW" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Usage : deploy/release.sh MAJEUR.MINEUR.CORRECTIF (ex. 1.1.0)" >&2; exit 1; }
OLD="$(cat VERSION)"
TAG="v$NEW"

[ "$(git branch --show-current)" = "main" ] || { echo "Placez-vous sur la branche main." >&2; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "Des modifications ne sont pas commitées : commitez-les d'abord." >&2; exit 1; }
git rev-parse -q --verify "refs/tags/$TAG" >/dev/null && { echo "La version $TAG existe déjà." >&2; exit 1; }
[ "$(printf '%s\n%s\n' "$OLD" "$NEW" | sort -V | tail -1)" = "$NEW" ] && [ "$OLD" != "$NEW" ] \
  || { echo "La nouvelle version ($NEW) doit être supérieure à la version actuelle ($OLD)." >&2; exit 1; }

# Il doit y avoir quelque chose sous « Non publié ».
UNRELEASED="$(awk '/^## \[Non publié\]/{f=1; next} /^## \[/{f=0} f' CHANGELOG.md | grep -v '^[[:space:]]*$' || true)"
[ -n "$UNRELEASED" ] || { echo "CHANGELOG.md : rien sous « ## [Non publié] ». Décrivez les nouveautés avant de publier." >&2; exit 1; }

echo "$NEW" > VERSION
python3 - "$NEW" <<'PY'
import datetime, sys
new = sys.argv[1]
text = open("CHANGELOG.md", encoding="utf-8").read()
marker = "## [Non publié]"
text = text.replace(marker, f"{marker}\n\n## [{new}] - {datetime.date.today().isoformat()}", 1)
open("CHANGELOG.md", "w", encoding="utf-8").write(text)
PY

git add VERSION CHANGELOG.md
git commit -q -m "Version $NEW"
git tag -a "$TAG" -m "Version $NEW"
echo "Version $OLD -> $NEW prête (commit + étiquette $TAG créés, rien n'est encore envoyé)."
echo "Pour la publier :  git push origin main && git push origin $TAG"
