"""Empresas (clientes SaaS) e respectivos perfis padrão."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, contexto_actual, exige_superadmin
from app.models import Company, CompanyUser, agora
from app.schemas import EmpresaActualizar, EmpresaCriar, EmpresaSaida, Pagina
from app.services.auditoria import auditar, serializar
from app.services.perfis import criar_perfis_empresa

router = APIRouter(prefix="/companies", tags=["Empresas"])


def _obter(db: Session, ctx: Contexto, company_id: str) -> Company:
    empresa = db.get(Company, company_id)
    if empresa is None or empresa.eliminado_em is not None:
        raise HTTPException(404, "Empresa não encontrada")
    if not ctx.superadmin:
        membro = db.scalar(select(CompanyUser).where(
            CompanyUser.company_id == company_id, CompanyUser.user_id == ctx.utilizador.id,
            CompanyUser.activo.is_(True)))
        if membro is None:
            raise HTTPException(403, "Não tem acesso a esta empresa")
    return empresa


@router.get("", response_model=Pagina[EmpresaSaida], summary="Listar empresas")
def listar(skip: int = 0, limit: int = 50, ctx: Contexto = Depends(contexto_actual),
           db: Session = Depends(get_db)):
    consulta = select(Company).where(Company.eliminado_em.is_(None)).order_by(Company.nome)
    if not ctx.superadmin:
        consulta = consulta.join(CompanyUser, CompanyUser.company_id == Company.id).where(
            CompanyUser.user_id == ctx.utilizador.id, CompanyUser.activo.is_(True))
    total, items = paginar(db, consulta, skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=EmpresaSaida, status_code=201, summary="Criar empresa (super admin)")
def criar(dados: EmpresaCriar, ctx: Contexto = Depends(exige_superadmin), db: Session = Depends(get_db)):
    if db.scalar(select(Company).where(Company.slug == dados.slug)):
        raise HTTPException(409, "Já existe uma empresa com este slug")
    empresa = Company(**dados.model_dump())
    db.add(empresa)
    db.flush()
    criar_perfis_empresa(db, empresa.id)
    auditar(db, ctx, "criar", "company", empresa.id, depois=serializar(empresa))
    db.commit()
    return empresa


@router.get("/{company_id}", response_model=EmpresaSaida, summary="Consultar empresa")
def obter(company_id: str, ctx: Contexto = Depends(contexto_actual), db: Session = Depends(get_db)):
    return _obter(db, ctx, company_id)


@router.patch("/{company_id}", response_model=EmpresaSaida, summary="Actualizar empresa")
def actualizar(company_id: str, dados: EmpresaActualizar, ctx: Contexto = Depends(contexto_actual),
               db: Session = Depends(get_db)):
    empresa = _obter(db, ctx, company_id)
    if not ctx.superadmin and ("companies", "edit") not in ctx.permissoes:
        raise HTTPException(403, "Sem permissão para alterar a empresa")
    antes = serializar(empresa)
    for campo, valor in dados.model_dump(exclude_unset=True).items():
        setattr(empresa, campo, valor)
    auditar(db, ctx, "actualizar", "company", empresa.id, antes=antes, depois=serializar(empresa))
    db.commit()
    return empresa


@router.delete("/{company_id}", status_code=204, summary="Desactivar empresa (soft delete, super admin)")
def eliminar(company_id: str, ctx: Contexto = Depends(exige_superadmin), db: Session = Depends(get_db)):
    empresa = _obter(db, ctx, company_id)
    antes = serializar(empresa)
    empresa.activa = False
    empresa.eliminado_em = agora()
    auditar(db, ctx, "eliminar", "company", empresa.id, antes=antes)
    db.commit()
