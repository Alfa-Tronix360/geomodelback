"""Hash de senhas e tokens JWT."""
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_settings


def _bytes_senha(senha: str) -> bytes:
    """O bcrypt só considera os primeiros 72 bytes; truncamos de forma explícita."""
    return senha.encode("utf-8")[:72]


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(_bytes_senha(senha), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        return bcrypt.checkpw(_bytes_senha(senha), senha_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def criar_token(utilizador_id: str) -> str:
    s = get_settings()
    agora = datetime.now(timezone.utc)
    payload = {"sub": utilizador_id, "iat": agora, "exp": agora + timedelta(minutes=s.jwt_expira_minutos)}
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def descodificar_token(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])
