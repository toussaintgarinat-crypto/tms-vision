"""Fiches des ostéopathes : copier, modifier, créer, archiver (phases 3 et 4 du chantier « comptes,
validation et fiches »).

Règles (section 5 du plan, vérifiées par tests/test_sheets.py) :
- copier = un NOUVEL exercice, sans validation, dont l'auteur d'origine est repris à l'identique de
  l'original (jamais réécrit : copier une copie garde le tout premier auteur) ;
- toute modification crée une nouvelle version, sans validation ; l'ancienne version et ses
  validations restent en base ;
- seul le propriétaire (l'ostéopathe qui a créé ou copié la fiche) la modifie ; les fiches de fichier
  ne se modifient pas, on les copie ;
- une fiche ne se supprime jamais : elle est archivée (les copies, les envois et l'historique des
  validations continuent de s'y référer) ;
- créer, copier et modifier exigent le rôle ostéopathe, vérifié ici et non dans le site."""
import json
import re
import unicodedata
import uuid

from tms_vision import exercises, validation
from tms_vision.validation import ValidationError

# Champs qu'un ostéopathe peut fixer : le reste (id, statut, validation, fiche) est posé par le code.
EDITABLE_KEYS = (
    "zone", "title", "description", "view", "target_segments", "poses", "keyframes",
    "instructions", "duration_seconds", "position", "benefit",
)
_COPY_SUFFIX = " (copie)"


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:40].strip("-") or "fiche"


def _new_id(title: str, taken: set[str]) -> str:
    while True:
        candidate = f"{_slug(title)}-{uuid.uuid4().hex[:6]}"
        if candidate not in taken:
            return candidate


def _require_osteopath(user: dict | None) -> dict:
    return validation._require_osteopath(user)


def _clean(content: dict, exercise_id: str) -> dict:
    """Contenu complet d'une fiche d'ostéopathe : champs libres + champs posés par le code. Lève
    ValueError (message en français nommant le champ) si la fiche est invalide."""
    unknown = set(content) - set(EDITABLE_KEYS) - {"id"}
    if unknown:
        raise ValidationError(422, f"{sorted(unknown)[0]} : champ non modifiable ou inconnu.")
    data = {key: content[key] for key in EDITABLE_KEYS if key in content}
    data.update(
        id=exercise_id, status="draft", source="human", validated_by=None, validated_on=None,
    )
    try:
        exercises.validate_exercise(data, filename_stem=exercise_id)
    except ValueError as error:
        raise ValidationError(422, str(error)) from error
    return data


def _row(conn, exercise_id: str):
    return conn.execute(
        "SELECT id, origin, original_author, owner_id, archived_at FROM exercises WHERE id = ?",
        [exercise_id],
    ).fetchone()


def _insert_version(conn, data: dict, user: dict, number: int) -> str:
    version_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO exercise_versions VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            version_id, data["id"], number, json.dumps(data, ensure_ascii=False),
            validation.fingerprint(data), user["id"], validation._now(),
        ],
    )
    return version_id


def create(user: dict | None, content: dict) -> dict:
    """Crée une fiche : l'ostéopathe en est l'auteur d'origine et le propriétaire."""
    user = _require_osteopath(user)
    title = content.get("title")
    taken = {e["id"] for e in validation.load_effective_catalog(include_archived=True)}
    data = _clean(content, _new_id(title if isinstance(title, str) else "", taken))
    conn = validation._connect()
    try:
        conn.execute(
            "INSERT INTO exercises (id, origin, original_author, copied_from_exercise, "
            "copied_from_version, created_at, owner_id) VALUES (?, 'osteopathe', ?, NULL, NULL, ?, ?)",
            [data["id"], user["name"], validation._now(), user["id"]],
        )
        _insert_version(conn, data, user, 1)
    finally:
        conn.close()
    validation._audit("exercise.create", user, data["id"])
    return data


def copy(user: dict | None, source_id: str) -> dict:
    """Copie la fiche `source_id` (de fichier, d'un confrère ou la sienne) : nouvel exercice sans
    validation. L'auteur d'origine est celui de l'original, repris tel quel."""
    user = _require_osteopath(user)
    source = validation.get_exercise(source_id)
    if source is None:
        raise ValidationError(404, "Exercice introuvable.")
    taken = {e["id"] for e in validation.load_effective_catalog(include_archived=True)}
    new_id = _new_id(source["title"], taken)
    content = {key: source[key] for key in EDITABLE_KEYS if key in source}
    content["title"] = source["title"] + _COPY_SUFFIX
    data = _clean(content, new_id)
    conn = validation._connect()
    try:
        source_row = _row(conn, source_id)
        author = source_row[2] if source_row else validation.original_author(source)
        source_version = validation._ensure_version(conn, source)
        conn.execute(
            "INSERT INTO exercises (id, origin, original_author, copied_from_exercise, "
            "copied_from_version, created_at, owner_id, copied_from_title) "
            "VALUES (?, 'osteopathe', ?, ?, ?, ?, ?, ?)",
            [
                new_id, author, source_id, source_version, validation._now(), user["id"],
                source["title"],
            ],
        )
        _insert_version(conn, data, user, 1)
    finally:
        conn.close()
    validation._audit("exercise.copy", user, new_id)
    return data


def _owned_row(conn, user: dict, exercise_id: str):
    row = _row(conn, exercise_id)
    if row is None or row[1] == "file":
        raise ValidationError(
            409, "Cette fiche est une fiche d'origine : copiez-la pour obtenir votre version."
        )
    if row[3] != user["id"]:
        raise ValidationError(403, "Seul l'ostéopathe qui a créé cette fiche peut la modifier.")
    return row


def update(user: dict | None, exercise_id: str, changes: dict) -> dict:
    """Modifie une fiche dont `user` est propriétaire. Une modification crée une nouvelle version,
    donc sans validation ; rien ne change si le contenu est identique."""
    user = _require_osteopath(user)
    if validation.get_exercise(exercise_id) is None:
        raise ValidationError(404, "Exercice introuvable.")
    conn = validation._connect()
    try:
        row = _owned_row(conn, user, exercise_id)
        if row[4] is not None:
            raise ValidationError(409, "Cette fiche est archivée : désarchivez-la d'abord.")
        current = validation.get_exercise(exercise_id)
        base = {key: current[key] for key in EDITABLE_KEYS if key in current}
        data = _clean({**base, **changes}, exercise_id)
        if validation.fingerprint(data) == validation.fingerprint(current):
            return current
        number = conn.execute(
            "SELECT max(number) + 1 FROM exercise_versions WHERE exercise_id = ?", [exercise_id]
        ).fetchone()[0]
        _insert_version(conn, data, user, number)
    finally:
        conn.close()
    validation._audit("exercise.update", user, exercise_id)
    return data


def set_archived(user: dict | None, exercise_id: str, archived: bool) -> dict:
    """Archive (ou désarchive) une fiche dont `user` est propriétaire. Pas de suppression : les
    copies, les envois et les validations s'y réfèrent."""
    user = _require_osteopath(user)
    if validation.get_exercise(exercise_id) is None:
        raise ValidationError(404, "Exercice introuvable.")
    conn = validation._connect()
    try:
        _owned_row(conn, user, exercise_id)
        conn.execute(
            "UPDATE exercises SET archived_at = ? WHERE id = ?",
            [validation._now() if archived else None, exercise_id],
        )
    finally:
        conn.close()
    validation._audit("exercise.archive" if archived else "exercise.unarchive", user, exercise_id)
    return validation.get_exercise(exercise_id)


def list_mine(user: dict | None) -> list[dict]:
    """Fiches dont `user` est propriétaire (archivées comprises), avec leur étiquette."""
    user = _require_osteopath(user)
    conn = validation._connect()
    try:
        ids = [
            row[0] for row in conn.execute(
                "SELECT id FROM exercises WHERE owner_id = ? ORDER BY created_at DESC", [user["id"]]
            ).fetchall()
        ]
    finally:
        conn.close()
    by_id = {e["id"]: e for e in validation.load_effective_catalog(include_archived=True)}
    sheets = [by_id[i] for i in ids if i in by_id]
    labels = validation.labels_for(sheets, user["id"])
    return [{"exercise": sheet, "label": labels[sheet["id"]]} for sheet in sheets]


def copies_of(exercise_id: str) -> int:
    conn = validation._connect()
    try:
        return conn.execute(
            "SELECT count(*) FROM exercises WHERE copied_from_exercise = ?", [exercise_id]
        ).fetchone()[0]
    finally:
        conn.close()
