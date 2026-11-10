"""Semeia permissões, o super administrador e, opcionalmente, uma empresa demo.

Uso:
    python scripts/seed.py
    python scripts/seed.py --sem-demo
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from sqlalchemy import select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, SessionLocal, engine  # noqa: E402
from app.models import (  # noqa: E402
    AssayResult, Company, CompanyUser, DrillHole, DrillInterval, DrillSurvey,
    GeologicalDomain, GeologicalModel, Laboratory, Lithology, ModelVersion, Project,
    ResourceEstimate, Sample, User,
)
from app.security import hash_senha  # noqa: E402
from app.services.geo import calcular_estimativa  # noqa: E402
from app.services.perfis import criar_perfis_empresa, semear_permissoes  # noqa: E402


def _utilizador(db, nome: str, email: str, senha: str, empresa: Company | None = None,
                papel=None, superadmin: bool = False) -> User:
    email = email.strip().lower()
    utilizador = db.scalar(select(User).where(User.email == email))
    if utilizador is None:
        utilizador = User(nome=nome, email=email, senha_hash=hash_senha(senha),
                          superadmin=superadmin, activo=True)
        db.add(utilizador)
        db.flush()
    else:
        utilizador.superadmin = utilizador.superadmin or superadmin
    if empresa is not None and papel is not None:
        membro = db.scalar(select(CompanyUser).where(
            CompanyUser.company_id == empresa.id, CompanyUser.user_id == utilizador.id))
        if membro is None:
            db.add(CompanyUser(company_id=empresa.id, user_id=utilizador.id,
                               role_id=papel.id, activo=True))
    return utilizador


def _criar_demo(db, empresa: Company) -> None:
    papeis = {papel.codigo: papel for papel in criar_perfis_empresa(db, empresa.id)}
    gestor = _utilizador(db, "Gestor Demo", "gestor@clacs.ao", "Demo12345",
                         empresa, papeis["company_admin"])
    geologo = _utilizador(db, "Geólogo Demo", "geologo@clacs.ao", "Demo12345",
                          empresa, papeis["geologist"])
    _utilizador(db, "Técnico de Laboratório Demo", "laboratorio@clacs.ao", "Demo12345",
                empresa, papeis["lab_technician"])
    _utilizador(db, "Engenheiro de Minas Demo", "engenheiro@clacs.ao", "Demo12345",
                empresa, papeis["mining_engineer"])
    _utilizador(db, "Auditor Demo", "auditor@clacs.ao", "Demo12345",
                empresa, papeis["auditor"])

    if db.scalar(select(Project).where(Project.company_id == empresa.id).limit(1)):
        return

    projeto_cobre = Project(
        company_id=empresa.id, codigo="PRJ-001", nome="Projecto Cobre Catoca",
        descricao="Projecto de exploração de cobre no leste de Angola.",
        mineral="Cobre", concessao="CONC-2026-001", provincia="Lunda Sul",
        municipio="Catoca", area_km2=120.5, estado="activo", gestor_id=gestor.id,
        geometria={"type": "Point", "coordinates": [20.1, -9.4]},
    )
    projeto_ouro = Project(
        company_id=empresa.id, codigo="PRJ-002", nome="Projecto Ouro Luena",
        descricao="Alvos auríferos na província do Moxico.",
        mineral="Ouro", concessao="CONC-2026-002", provincia="Moxico",
        municipio="Luena", area_km2=85.0, estado="planeado", gestor_id=geologo.id,
        geometria={"type": "Point", "coordinates": [19.9, -11.8]},
    )
    db.add_all([projeto_cobre, projeto_ouro])
    db.flush()

    litologias = {}
    for codigo, nome, cor in (
        ("GRN", "Granito", "#d9a066"),
        ("XST", "Xisto", "#6b8e23"),
        ("QTZ", "Quartzito", "#d3d3d3"),
    ):
        litologia = Lithology(company_id=empresa.id, codigo=codigo, nome=nome, cor=cor)
        db.add(litologia)
        litologias[codigo] = litologia
    db.flush()

    furos = []
    for codigo, nome, x, y, z, prevista, final, estado in (
        ("FUR-001", "Furo de confirmação 1", 10.0, 20.0, 1200.0, 250.0, 180.0, "concluido"),
        ("FUR-002", "Furo de extensão 2", 35.0, 42.0, 1185.0, 300.0, 220.0, "em_sondagem"),
    ):
        furo = DrillHole(
            company_id=empresa.id, project_id=projeto_cobre.id, codigo=codigo, nome=nome,
            tipo="diamantado", estado=estado, x=x, y=y, z=z, azimute=90.0, inclinacao=-60.0,
            profundidade_prevista=prevista, profundidade_final=final, sonda="RIG-01",
            geologo_id=geologo.id,
        )
        db.add(furo)
        furos.append(furo)
    db.flush()

    for furo in furos:
        for profundidade, azimute, inclinacao in (
            (0.0, 90.0, -60.0), (50.0, 91.0, -61.0), (100.0, 92.0, -62.0),
            (150.0, 93.0, -63.0),
        ):
            if profundidade <= (furo.profundidade_final or 0):
                db.add(DrillSurvey(company_id=empresa.id, drill_hole_id=furo.id,
                                   profundidade=profundidade, azimute=azimute,
                                   inclinacao=inclinacao, metodo="gyro"))
        for de, ate, codigo_litologia, alteracao in (
            (0.0, 20.0, "GRN", "Sã"), (20.0, 80.0, "XST", "Sericitização"),
            (80.0, furo.profundidade_final or 100.0, "QTZ", "Silicificação"),
        ):
            db.add(DrillInterval(
                company_id=empresa.id, drill_hole_id=furo.id, de=de, ate=ate,
                lithology_id=litologias[codigo_litologia].id, alteracao=alteracao,
                recuperacao_pct=95.0, rqd_pct=80.0,
            ))
    db.flush()

    laboratorio = Laboratory(
        company_id=empresa.id, codigo="ALS", nome="ALS Angola",
        contacto="Laboratório ALS", email="lab@als.ao", telefone="+244 923 000 000",
        pais="Angola", acreditacao="ISO/IEC 17025",
    )
    db.add(laboratorio)
    db.flush()

    amostras = []
    for codigo, de, ate, furo in (
        ("AM-001", 10.0, 12.0, furos[0]),
        ("AM-002", 30.0, 32.0, furos[0]),
        ("AM-003", 90.0, 92.0, furos[0]),
        ("AM-004", 40.0, 42.0, furos[1]),
    ):
        amostra = Sample(
            company_id=empresa.id, project_id=projeto_cobre.id, drill_hole_id=furo.id,
            codigo=codigo, tipo="testemunho", de=de, ate=ate, peso_kg=5.5,
            estado="analisada", recolhido_por=geologo.nome,
        )
        db.add(amostra)
        amostras.append(amostra)
    db.flush()

    for amostra, parametro, valor, unidade, metodo in (
        (amostras[0], "Cu", 1.2, "%", "ICP-OES"),
        (amostras[1], "Cu", 0.8, "%", "ICP-OES"),
        (amostras[2], "Au", 0.5, "ppm", "Fire Assay"),
        (amostras[3], "Cu", 0.65, "%", "ICP-OES"),
    ):
        db.add(AssayResult(
            company_id=empresa.id, sample_id=amostra.id, laboratory_id=laboratorio.id,
            parametro=parametro, valor=valor, unidade=unidade, metodo=metodo,
            estado="validado", validado_por=gestor.id,
        ))

    modelo = GeologicalModel(
        company_id=empresa.id, project_id=projeto_cobre.id, nome="Modelo Geológico 2026",
        descricao="Modelo de domínios mineralizados do Projecto Cobre Catoca.",
        tipo="combinado", estado="validado", versao_actual=1, criado_por=geologo.id,
    )
    db.add(modelo)
    db.flush()
    db.add(GeologicalDomain(
        company_id=empresa.id, model_id=modelo.id, codigo="DOM-1",
        nome="Domínio mineralizado principal", cor="#ff6600",
        lithology_id=litologias["QTZ"].id,
    ))
    db.add(ModelVersion(
        company_id=empresa.id, model_id=modelo.id, numero_versao=1,
        nome="Versão inicial", estado="validado", formato="obj",
        ficheiro_chave="modelos/catoca-v1.obj", ficheiro_url="https://files.local/catoca-v1.obj",
        criado_por=geologo.id, validado_por=gestor.id,
        metadados={"vertices": 152340, "faces": 304680},
    ))

    volume, densidade, teor = 1_000_000.0, 2.7, 1.2
    tonelagem, metal = calcular_estimativa(volume, densidade, teor, "%")
    db.add(ResourceEstimate(
        company_id=empresa.id, project_id=projeto_cobre.id, model_id=modelo.id,
        nome="Estimativa inicial de cobre", metodo="idw", commodity="Cu",
        teor_corte=teor, unidade_teor="%", densidade=densidade, estado="validado",
        volume_m3=volume, tonelagem=tonelagem, metal_contido=metal,
        parametros={"blocos": 12000, "dimensao_bloco_m": [10, 10, 5]},
        versao=1, criado_por=geologo.id, validado_por=gestor.id,
    ))
    db.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="Semeia a base de dados do CLACS GeoModel")
    parser.add_argument("--sem-demo", action="store_true", help="Não criar a empresa e dados demo")
    argumentos = parser.parse_args()

    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        semear_permissoes(db)
        _utilizador(db, "Administrador CLACS", settings.admin_email, settings.admin_password,
                    superadmin=True)

        if not argumentos.sem_demo:
            empresa = db.scalar(select(Company).where(Company.slug == "clacs-demo"))
            if empresa is None:
                empresa = Company(
                    nome="CLACS Mineração Demo", slug="clacs-demo", nif="5000000000",
                    pais="Angola", provincia="Luanda", cidade="Luanda", moeda="AOA",
                    fuso_horario="Africa/Luanda",
                )
                db.add(empresa)
                db.flush()
            _criar_demo(db, empresa)

        db.commit()
        print("Base de dados semeada com sucesso.")
        print(f"Super administrador: {settings.admin_email}")
        if not argumentos.sem_demo:
            print("Empresa demo: clacs-demo")
            print("Gestor demo: gestor@clacs.ao / Demo12345")
            print("Geólogo demo: geologo@clacs.ao / Demo12345")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
