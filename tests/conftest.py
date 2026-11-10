"""Configuração dos testes: base SQLite isolada, empresas e utilizadores de teste."""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

BASE_TESTE = RAIZ / "test_geomodel.db"
os.environ["DATABASE_URL"] = f"sqlite:///{BASE_TESTE.as_posix()}"
os.environ["JWT_SECRET"] = "segredo-de-teste-com-pelo-menos-32-caracteres"
os.environ["ADMIN_EMAIL"] = "admin@teste.ao"
os.environ["ADMIN_PASSWORD"] = "admin12345"
os.environ["AUTO_CRIAR_TABELAS"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Company, CompanyUser, User  # noqa: E402
from app.security import hash_senha  # noqa: E402
from app.services.perfis import criar_perfis_empresa  # noqa: E402


@pytest.fixture()
def bd():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        empresa_a = Company(nome="Empresa A", slug="empresa-a", provincia="Luanda")
        empresa_b = Company(nome="Empresa B", slug="empresa-b", provincia="Benguela")
        db.add_all([empresa_a, empresa_b])
        db.flush()
        papeis_a = {papel.codigo: papel for papel in criar_perfis_empresa(db, empresa_a.id)}
        papeis_b = {papel.codigo: papel for papel in criar_perfis_empresa(db, empresa_b.id)}

        def criar(nome: str, email: str, senha: str, empresa: Company | None = None,
                  papel=None, superadmin: bool = False) -> User:
            utilizador = User(nome=nome, email=email, senha_hash=hash_senha(senha),
                              superadmin=superadmin, activo=True)
            db.add(utilizador)
            db.flush()
            if empresa is not None and papel is not None:
                db.add(CompanyUser(company_id=empresa.id, user_id=utilizador.id,
                                   role_id=papel.id, activo=True))
            return utilizador

        criar("Super Admin", "super@teste.ao", "super12345", superadmin=True)
        criar("Admin A", "admin.a@teste.ao", "admin12345", empresa_a, papeis_a["company_admin"])
        criar("Geólogo A", "geologo.a@teste.ao", "geo12345", empresa_a, papeis_a["geologist"])
        criar("Lab A", "lab.a@teste.ao", "lab12345", empresa_a, papeis_a["lab_technician"])
        criar("Admin B", "admin.b@teste.ao", "admin12345", empresa_b, papeis_b["company_admin"])
        db.commit()
        yield {
            "empresa_a": empresa_a.id,
            "empresa_b": empresa_b.id,
            "role_geologo_a": papeis_a["geologist"].id,
            "role_admin_a": papeis_a["company_admin"].id,
            "role_lab_a": papeis_a["lab_technician"].id,
        }
    finally:
        db.close()


@pytest.fixture()
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def autenticar(cliente):
    def _login(email: str, senha: str, company_id: str | None = None) -> dict[str, str]:
        resposta = cliente.post("/auth/login", json={"email": email, "senha": senha})
        assert resposta.status_code == 200, resposta.text
        cabecalhos = {"Authorization": f"Bearer {resposta.json()['access_token']}"}
        if company_id:
            cabecalhos["X-Company-ID"] = company_id
        return cabecalhos
    return _login


@pytest.fixture()
def superadmin(autenticar):
    return autenticar("super@teste.ao", "super12345")


@pytest.fixture()
def admin_a(autenticar, bd):
    return autenticar("admin.a@teste.ao", "admin12345", bd["empresa_a"])


@pytest.fixture()
def admin_b(autenticar, bd):
    return autenticar("admin.b@teste.ao", "admin12345", bd["empresa_b"])


@pytest.fixture()
def geologo_a(autenticar, bd):
    return autenticar("geologo.a@teste.ao", "geo12345", bd["empresa_a"])


@pytest.fixture()
def lab_a(autenticar, bd):
    return autenticar("lab.a@teste.ao", "lab12345", bd["empresa_a"])


@pytest.fixture()
def criar_projecto(cliente, admin_a):
    def _criar(codigo: str = "PRJ-001", nome: str = "Projecto Teste", **extra) -> dict:
        dados = {"codigo": codigo, "nome": nome, "estado": "activo", "area_km2": 10.0,
                 "mineral": "Cobre"}
        dados.update(extra)
        resposta = cliente.post("/projects", json=dados, headers=admin_a)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()
    return _criar


@pytest.fixture()
def criar_furo(cliente, admin_a):
    def _criar(project_id: str, codigo: str = "F-001", **extra) -> dict:
        dados = {
            "project_id": project_id, "codigo": codigo, "x": 0.0, "y": 0.0, "z": 100.0,
            "azimute": 90.0, "inclinacao": -60.0, "profundidade_prevista": 200.0,
            "profundidade_final": 150.0, "estado": "concluido",
        }
        dados.update(extra)
        resposta = cliente.post("/drill-holes", json=dados, headers=admin_a)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()
    return _criar


@pytest.fixture()
def criar_laboratorio(cliente, admin_a):
    def _criar(codigo: str = "LAB-1", nome: str = "Laboratório Teste") -> dict:
        resposta = cliente.post("/laboratories", json={"codigo": codigo, "nome": nome},
                                headers=admin_a)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()
    return _criar
