from __future__ import annotations

import re
from datetime import date
from typing import Any


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_RE = re.compile(r"^[a-z0-9_.]{2,32}$")
PASSWORD_MIN_LENGTH = 16
PASSWORD_MAX_LENGTH = 4096
COMMON_PASSWORDS = {
    "password", "password123", "password1234", "123456789", "1234567890",
    "qwertyuiop", "letmein", "changeme", "adminadmin", "administrator",
    "welcome123", "discord123",
}


class ValidationError(ValueError):
    pass


def text(value: Any, *, field: str, required: bool = False, max_len: int = 1024) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValidationError(f"{field} é obrigatório.")
    if len(result) > max_len:
        raise ValidationError(f"{field} excede o tamanho permitido.")
    return result


def validate_password_strength(
    password: Any,
    *,
    email: str = "",
    username: str = "",
    field: str = "Senha",
) -> str:
    value = str(password or "")
    if not value:
        raise ValidationError(f"{field} é obrigatória.")
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValidationError(f"{field} deve ter pelo menos {PASSWORD_MIN_LENGTH} caracteres.")
    if len(value) > PASSWORD_MAX_LENGTH:
        raise ValidationError(f"{field} excede o tamanho permitido.")

    folded = value.casefold()
    if folded in COMMON_PASSWORDS:
        raise ValidationError(f"{field} é muito comum. Escolha uma senha exclusiva.")
    if len(set(value)) < 6:
        raise ValidationError(f"{field} precisa ter maior diversidade de caracteres.")

    identifiers = []
    email_value = (email or "").strip().casefold()
    if email_value:
        identifiers.append(email_value)
        local_part = email_value.split("@", 1)[0]
        if len(local_part) >= 4:
            identifiers.append(local_part)
    username_value = (username or "").strip().casefold()
    if len(username_value) >= 4:
        identifiers.append(username_value)
    for identifier in identifiers:
        if identifier and identifier in folded:
            raise ValidationError(f"{field} não deve conter seu e-mail ou nome de usuário.")
    return value


def validate_login(identifier: Any, password: Any) -> tuple[str, str]:
    identifier_s = text(identifier, field="Identificador", required=True, max_len=999)
    password_s = str(password or "")
    if not password_s:
        raise ValidationError("Senha é obrigatória.")
    if len(password_s) > 4096:
        raise ValidationError("Senha excede o tamanho permitido.")
    return identifier_s, password_s


def validate_registration(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    email = text(payload.get("email"), field="E-mail", required=True, max_len=320).lower()
    if not EMAIL_RE.fullmatch(email):
        raise ValidationError("E-mail inválido.")
    raw_password = payload.get("password")

    metadata_in = payload.get("profile") or {}
    if not isinstance(metadata_in, dict):
        raise ValidationError("Perfil inválido.")
    metadata: dict[str, Any] = {}

    global_name = text(metadata_in.get("global_name"), field="Nome de exibição", max_len=32)
    if global_name:
        metadata["global_name"] = global_name

    username = text(metadata_in.get("username"), field="Nome de usuário", required=True, max_len=32).lower()
    if ".." in username:
        raise ValidationError("Nome de usuário não pode conter pontos repetidos.")
    if not USERNAME_RE.fullmatch(username):
        raise ValidationError("Nome de usuário deve ter entre 2 e 32 caracteres e usar apenas letras, números, sublinhados _ ou pontos.")
    metadata["username"] = username
    password = validate_password_strength(raw_password, email=email, username=username)

    dob = text(metadata_in.get("date_of_birth"), field="Data de nascimento", required=True, max_len=10)
    try:
        parsed = date.fromisoformat(dob)
    except ValueError as exc:
        raise ValidationError("Data de nascimento inválida.") from exc
    if parsed >= date.today():
        raise ValidationError("Data de nascimento inválida.")
    metadata["date_of_birth"] = parsed.isoformat()
    metadata["marketing_opt_in"] = bool(payload.get("marketingOptIn", False))

    return email, password, metadata
