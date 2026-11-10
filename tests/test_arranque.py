"""O arranque cria o super administrador numa base vazia e permite repor a senha."""
from sqlalchemy import func, select

from app.config import get_settings
from app.database import SessionLocal
from app.models import User
from app.services.arranque import preparar_base_de_dados


def _login(cliente, senha):
    return cliente.post("/auth/login", json={"email": "admin@teste.ao", "senha": senha})


def test_arranque_cria_admin_e_repoe_senha(cliente, monkeypatch):
    preparar_base_de_dados()
    preparar_base_de_dados()  # idempotente
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.email == "admin@teste.ao")) == 1
    assert _login(cliente, "admin12345").status_code == 200

    settings = get_settings()
    monkeypatch.setattr(settings, "admin_password", "nova-senha-123")
    preparar_base_de_dados()
    assert _login(cliente, "nova-senha-123").status_code == 401  # sem a flag não mexe na senha

    monkeypatch.setattr(settings, "admin_repor_senha", True)
    preparar_base_de_dados()
    assert _login(cliente, "nova-senha-123").status_code == 200
