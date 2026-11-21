"""Commandes d'administration des comptes, à lancer sur le serveur (jamais par une page publique).

    ./tms create-admin [--email ADRESSE] [--name NOM]       crée le premier administrateur
    ./tms reset-password --email ADRESSE                    pose un nouveau mot de passe

Avec Docker : docker compose exec api python -m tms_vision.admin_cli create-admin

Le mot de passe est demandé sans écho ; pour un script, la variable TMS_ADMIN_PASSWORD le fournit
(jamais en argument : il apparaîtrait dans la liste des processus)."""
import argparse
import getpass
import os
import sys

from tms_vision import accounts


def _password(prompt: str, confirm: bool = True) -> str:
    given = os.environ.get("TMS_ADMIN_PASSWORD")
    if given:
        return given
    first = getpass.getpass(prompt)
    if confirm and getpass.getpass("Confirmez le mot de passe : ") != first:
        raise accounts.AccountError("password_mismatch", "Les deux mots de passe diffèrent.")
    return first


def create_admin(email: str | None, name: str | None) -> dict:
    """Crée un administrateur ; refuse si un administrateur actif existe déjà (le suivant se crée
    depuis l'écran d'administration)."""
    if any(user["active"] and "administrateur" in user["roles"] for user in accounts.list_users()):
        raise accounts.AccountError(
            "admin_exists",
            "Un administrateur existe déjà : créez les autres comptes depuis l'écran d'administration.",
        )
    email = email or input("Adresse email de l'administrateur : ")
    name = name or input("Nom affiché : ")
    # Un administrateur seul fait aussi le travail d'un praticien : on lui donne les deux rôles.
    user = accounts.create_user(
        email, name, _password("Mot de passe (12 caractères au moins) : "), ["praticien", "administrateur"]
    )
    accounts.audit("admin.create_cli", target=user["id"])
    return user


def reset_password(email: str) -> None:
    address = accounts.normalize_email(email)
    match = next((user for user in accounts.list_users() if user["email"] == address), None)
    if match is None:
        raise accounts.AccountError("not_found", "Aucun compte avec cette adresse.")
    accounts.admin_set_password(match["id"], _password("Nouveau mot de passe : "))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tms", description="Administration des comptes TMS Vision")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create-admin", help="crée le premier administrateur")
    create.add_argument("--email")
    create.add_argument("--name")
    reset = commands.add_parser("reset-password", help="pose un nouveau mot de passe")
    reset.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "create-admin":
            user = create_admin(args.email, args.name)
            print(f"Administrateur créé : {user['email']}. Connectez-vous sur le site avec cette adresse.")
        else:
            reset_password(args.email)
            print("Mot de passe modifié ; toutes les sessions de ce compte sont fermées.")
    except accounts.AccountError as error:
        print(f"Erreur : {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
