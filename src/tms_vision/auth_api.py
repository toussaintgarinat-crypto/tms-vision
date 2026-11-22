"""Routes de connexion et protection de l'API par comptes (phase 1).

La protection s'active dès qu'un compte existe, ou si `TMS_REQUIRE_AUTH=true` : une installation
qui n'a pas encore créé son premier administrateur continue de fonctionner comme avant (le mot de
passe commun posé par Caddy reste alors la seule barrière). Une fois active, toute route exige une
session, sauf la connexion et ce que reçoit un patient avec son lien (sa page d'exercices et les
vidéos), protégé par le jeton aléatoire de l'adresse.

Session : jeton aléatoire dans un cookie HttpOnly, SameSite=Lax, Secure derrière HTTPS. Les droits
sont vérifiés ici, côté API : le site n'est qu'une façade."""
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

from tms_vision import accounts, user_email

COOKIE_NAME = "tms_session"
_TRUE = {"1", "true", "yes", "oui", "on"}

# Ce qu'un patient atteint sans compte (même liste que le Caddyfile : lecture seule).
_PUBLIC_PATTERNS = (
    re.compile(r"^/library/shares/[^/]+$"),
    re.compile(r"^/capsules/[^/]+/video$"),
)
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ALWAYS_PUBLIC = {"/auth/login", "/auth/status", "/auth/setup", "/auth/recover", "/docs", "/openapi.json"}
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

_users_exist = False


def reset_cache() -> None:
    """Oublie le résultat mis en cache (tests, ou base remplacée)."""
    global _users_exist
    _users_exist = False


def auth_required() -> bool:
    """Vrai si l'API doit exiger une connexion : un compte existe, ou TMS_REQUIRE_AUTH est posé."""
    global _users_exist
    if os.environ.get("TMS_REQUIRE_AUTH", "").strip().lower() in _TRUE:
        return True
    if _users_exist:
        return True
    _users_exist = accounts.has_users()
    return _users_exist


def _is_public(method: str, path: str) -> bool:
    if path in _ALWAYS_PUBLIC:
        return True
    return method in ("GET", "HEAD") and any(pattern.match(path) for pattern in _PUBLIC_PATTERNS)


def local_setup_open(request: Request | None = None) -> bool:
    """L'écran « Créer votre compte » est ouvert : application de bureau (TMS_LOCAL_SETUP, l'API
    n'écoute que sur 127.0.0.1), aucun compte, et requête venue de cette machine."""
    if not desktop_mode() or accounts.has_users():
        return False
    return request is None or local_setup_origin(request)


def local_setup_origin(request: Request) -> bool:
    """La requête vient de cette machine (et n'a pas été relayée par un proxy)."""
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient") and not request.headers.get("x-forwarded-for")


def desktop_mode() -> bool:
    """Application de bureau (TMS_LOCAL_SETUP) : l'API n'écoute que sur cette machine."""
    return os.environ.get("TMS_LOCAL_SETUP", "").strip().lower() in _TRUE


def _client_address(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host if request.client else "-"


def _allowed_origins() -> set[str]:
    return {
        origin.strip().rstrip("/")
        for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }


def _origin_ok(request: Request) -> bool:
    """Contre les requêtes forgées depuis un autre site : une écriture qui porte un en-tête Origin
    doit venir du site lui-même (même hôte) ou d'une origine autorisée."""
    origin = request.headers.get("origin")
    if not origin or origin == "null":
        return origin is None
    origin = origin.rstrip("/")
    host = request.headers.get("host", "")
    return origin.split("://", 1)[-1] == host or origin in _allowed_origins() or origin in (
        "http://localhost:3000", "http://127.0.0.1:3000",
    )


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.user = None
        token = request.cookies.get(COOKIE_NAME)
        if token and auth_required():
            request.state.user = accounts.user_for_token(token)
        if request.method == "OPTIONS" or not auth_required() or _is_public(request.method, request.url.path):
            return await call_next(request)
        if request.state.user is None:
            return JSONResponse({"detail": "Connexion requise.", "code": "login_required"}, status_code=401)
        if request.method not in _SAFE_METHODS and not _origin_ok(request):
            return JSONResponse({"detail": "Origine de la requête refusée.", "code": "bad_origin"}, status_code=403)
        return await call_next(request)


def current_user(request: Request) -> dict:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user


def require_roles(*roles: str):
    """Dépendance FastAPI : le compte connecté doit avoir au moins un de ces rôles."""

    def dependency(user: dict = Depends(current_user)) -> dict:
        if not set(roles) & set(user["roles"]):
            raise HTTPException(status_code=403, detail="Droits insuffisants pour cette action.")
        return user

    return dependency


router = APIRouter(tags=["auth"])


class LoginBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class PasswordBody(BaseModel):
    current: str = Field(max_length=256)
    new: str = Field(max_length=256)


class PasswordOnlyBody(BaseModel):
    password: str = Field(max_length=256)


class EmailChangeBody(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=256)


class ProfileBody(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    language: str | None = Field(default=None, max_length=8)


def _set_cookie(request: Request, response: Response, token: str) -> None:
    secure = (
        os.environ.get("TMS_COOKIE_SECURE", "").strip().lower() in _TRUE
        or request.url.scheme == "https"
        or request.headers.get("x-forwarded-proto", "").lower() == "https"
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=accounts.SESSION_MAX_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
    )


def _raise(error: accounts.AccountError, status: int) -> None:
    headers = {"Retry-After": str(error.retry_after)} if error.retry_after else None
    raise HTTPException(
        status_code=status,
        detail={"message": str(error), "code": error.code, "retry_after": error.retry_after},
        headers=headers,
    )


@router.get("/auth/status")
def auth_status(request: Request):
    """Ce que le site doit afficher : connexion, création du premier compte, ou rien."""
    required = auth_required()
    return {
        "auth_required": required,
        "setup_required": not accounts.has_users(),
        "local_setup": local_setup_open(request),
        "desktop": desktop_mode(),
        "authenticated": getattr(request.state, "user", None) is not None,
        "user": getattr(request.state, "user", None),
    }


@router.post("/auth/login")
def login(body: LoginBody, request: Request, response: Response):
    try:
        user = accounts.authenticate(body.email, body.password, _client_address(request))
    except accounts.AccountError as error:
        _raise(error, 429 if error.code == "too_many_attempts" else 401)
    _set_cookie(request, response, accounts.create_session(user["id"]))
    reset_cache()
    return {"user": user}


class SetupBody(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(max_length=120)
    password: str = Field(max_length=256)
    # La personne déclare être ostéopathe : elle pourra valider des fiches sous son nom.
    osteopath: bool = False


@router.post("/auth/setup")
def setup_first_account(body: SetupBody, request: Request, response: Response):
    """Première utilisation de l'application de bureau : crée le compte administrateur, sans terminal.
    Fermé sur un serveur (là, `create-admin`) et dès qu'un compte existe."""
    if not local_setup_open(request):
        raise HTTPException(status_code=403, detail={"message": "Création du premier compte indisponible ici.", "code": "setup_closed"})
    try:
        user = accounts.create_first_admin(
            body.email, body.name, body.password, osteopath=body.osteopath
        )
    except accounts.AccountError as error:
        _raise(error, 409 if error.code == "setup_done" else 422)
    accounts.audit("login.success", user_id=user["id"], email=user["email"], address=_client_address(request))
    _set_cookie(request, response, accounts.create_session(user["id"]))
    reset_cache()
    return {"user": user, "recovery_code": accounts.new_recovery_code(user["id"])}


class RecoverBody(BaseModel):
    email: str = Field(max_length=254)
    code: str = Field(max_length=64)
    password: str = Field(max_length=256)


@router.post("/auth/recover")
def recover_password(body: RecoverBody, request: Request):
    """« Mot de passe oublié » de l'application de bureau : nouveau mot de passe avec le code de
    récupération montré à la création du compte. Fermé sur un serveur (l'administrateur réinitialise)."""
    if not desktop_mode() or not local_setup_origin(request):
        raise HTTPException(status_code=403, detail={"message": "Réinitialisation par code indisponible ici.", "code": "recover_closed"})
    try:
        code = accounts.reset_with_recovery_code(body.email, body.code, body.password, _client_address(request))
    except accounts.AccountError as error:
        _raise(error, 429 if error.code == "too_many_attempts" else 401 if error.code == "invalid_recovery" else 422)
    return {"recovery_code": code}


@router.post("/auth/recovery-code")
def regenerate_recovery_code(body: PasswordOnlyBody, user: dict = Depends(current_user)):
    """Nouveau code de récupération (l'ancien cesse de valoir), après vérification du mot de passe."""
    if not desktop_mode():
        raise HTTPException(status_code=403, detail={"message": "Code de récupération indisponible ici.", "code": "recover_closed"})
    try:
        accounts.authenticate(user["email"], body.password, "recovery-code")
        return {"recovery_code": accounts.new_recovery_code(user["id"])}
    except accounts.AccountError as error:
        _raise(error, 429 if error.code == "too_many_attempts" else 422)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    user = getattr(request.state, "user", None)
    accounts.revoke_session(token)
    if user:
        accounts.audit("logout", user_id=user["id"], email=user["email"], address=_client_address(request))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return {"user": user}


@router.patch("/auth/me")
def update_me(body: ProfileBody, user: dict = Depends(current_user)):
    try:
        updated = accounts.update_user(
            user["id"], name=body.name, language=body.language, actor=user["id"]
        )
    except accounts.AccountError as error:
        _raise(error, 422)
    return {"user": updated}


@router.post("/auth/email")
def change_my_email(body: EmailChangeBody, user: dict = Depends(current_user)):
    """Change l'adresse de connexion du compte, après vérification du mot de passe."""
    try:
        accounts.authenticate(user["email"], body.password, "email-change")
        return {"user": accounts.update_user(user["id"], email=body.email, actor=user["id"])}
    except accounts.AccountError as error:
        _raise(error, 429 if error.code == "too_many_attempts" else 422)


@router.post("/auth/password")
def change_password(body: PasswordBody, request: Request, user: dict = Depends(current_user)):
    try:
        accounts.change_password(
            user["id"], body.current, body.new, keep_token=request.cookies.get(COOKIE_NAME)
        )
    except accounts.AccountError as error:
        _raise(error, 422)
    return {"ok": True}


# --- Administration des comptes --------------------------------------------------------------

admin_router = APIRouter(prefix="/admin", tags=["admin"])
_admin = require_roles("administrateur")


class NewUserBody(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(max_length=120)
    password: str = Field(max_length=256)
    roles: list[str]
    language: str | None = None


class UserPatchBody(BaseModel):
    roles: list[str] | None = None
    active: bool | None = None
    name: str | None = Field(default=None, max_length=120)
    email: str | None = Field(default=None, max_length=254)


class ResetPasswordBody(BaseModel):
    password: str = Field(max_length=256)


@admin_router.get("/users")
def admin_list_users(_: dict = Depends(_admin)):
    return accounts.list_users()


@admin_router.post("/users", status_code=201)
def admin_create_user(body: NewUserBody, admin: dict = Depends(_admin)):
    try:
        return accounts.create_user(
            body.email, body.name, body.password, body.roles, language=body.language, actor=admin["id"]
        )
    except accounts.AccountError as error:
        _raise(error, 409 if error.code == "email_taken" else 422)


@admin_router.patch("/users/{user_id}")
def admin_update_user(user_id: str, body: UserPatchBody, admin: dict = Depends(_admin)):
    try:
        return accounts.update_user(
            user_id, roles=body.roles, active=body.active, name=body.name, email=body.email,
            actor=admin["id"],
        )
    except accounts.AccountError as error:
        _raise(error, {"not_found": 404, "email_taken": 409}.get(error.code, 422))


@admin_router.post("/users/{user_id}/password")
def admin_reset_password(user_id: str, body: ResetPasswordBody, admin: dict = Depends(_admin)):
    try:
        accounts.admin_set_password(user_id, body.password, actor=admin["id"])
    except accounts.AccountError as error:
        _raise(error, 404 if error.code == "not_found" else 422)
    return {"ok": True}


class InvitationBody(BaseModel):
    email: str = Field(max_length=254)
    name: str | None = Field(default=None, max_length=120)
    message: str | None = Field(default=None, max_length=2000)
    osteopath: bool = False


@admin_router.post("/invitations")
def admin_invite(body: InvitationBody, request: Request, admin: dict = Depends(_admin)):
    """Envoie à `email` l'invitation à installer l'application de bureau : liens directs vers les
    installateurs de la dernière version et guide du premier lancement (le compte se crée sur son
    ordinateur, pas ici). Part de l'adresse de l'administrateur, comme les envois d'exercices."""
    from tms_vision import mailer, updates, user_email

    recipient = body.email.strip()
    if not _EMAIL_PATTERN.match(recipient):
        raise HTTPException(status_code=422, detail="Adresse email invalide.")
    release = updates.fetch_latest_release()
    outgoing = mailer.build_invitation_message(
        to=recipient, inviter_name=admin["name"], invitee_name=(body.name or "").strip() or None,
        message=(body.message or "").strip() or None, osteopath=body.osteopath,
        release_url=release["url"] if release else mailer.RELEASES_PAGE_URL,
        downloads=mailer.installer_links(release["assets"]) if release else [],
    )
    try:
        service, reply_to = user_email.mailer_for(admin)
        if reply_to:
            import dataclasses

            outgoing = dataclasses.replace(outgoing, reply_to=reply_to)
        service.send(outgoing)
        status = "sent"
    except mailer.MailerError:
        status = "failed"
    else:
        if isinstance(service, mailer.NullMailer):
            status = "not_configured"
    accounts.audit(
        "invitation.send", user_id=admin["id"], email=admin["email"], target=recipient,
        detail=f"{status}; ostéopathe: {'oui' if body.osteopath else 'non'}",
    )
    return {"email_status": status}


@admin_router.get("/audit")
def admin_audit(limit: int = 200, _: dict = Depends(_admin)):
    return accounts.list_audit(limit)


# --- Mon email (adresse d'envoi du compte) ---------------------------------------------------

me_email_router = APIRouter(prefix="/me/email", tags=["email"])


class EmailSettingsBody(BaseModel):
    address: str = Field(max_length=254)
    host: str = Field(max_length=253)
    port: int
    security: str = Field(max_length=10)
    username: str = Field(default="", max_length=254)
    # Vide : on garde le mot de passe déjà enregistré.
    password: str | None = Field(default=None, max_length=256)


@me_email_router.get("")
def get_email_settings(user: dict = Depends(current_user)):
    return user_email.get_settings(user["id"])


@me_email_router.get("/suggest")
def suggest_email_settings(address: str, _: dict = Depends(current_user)):
    return {"suggestion": user_email.suggest(address)}


@me_email_router.put("")
def save_email_settings(body: EmailSettingsBody, user: dict = Depends(current_user)):
    try:
        return user_email.save_settings(user["id"], **body.model_dump())
    except accounts.AccountError as error:
        _raise(error, 422)


@me_email_router.delete("")
def delete_email_settings(user: dict = Depends(current_user)):
    user_email.delete_settings(user["id"])
    return user_email.get_settings(user["id"])


@me_email_router.post("/test")
def test_email_settings(user: dict = Depends(current_user)):
    try:
        return user_email.send_test(user)
    except accounts.AccountError as error:
        _raise(error, 422)
