"""Laboratórios de ensaio e acreditações."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import Laboratory
from app.schemas import (
    LaboratorioActualizar, LaboratorioCriar, LaboratorioSaida, Pagina,
)
from app.services.auditoria import auditar, serializar

router = APIRouter(prefix="/laboratories", tags=["Laboratórios"])


def _obter(db: Session, company_id: str, laboratory_id: str) -> Laboratory:
    laboratorio = db.get(Laboratory, laboratory_id)
    if laboratorio is None or laboratorio.company_id != company_id:
        raise HTTPException(404, "Laboratório não encontrado")
    return laboratorio


@router.get("", response_model=Pagina[LaboratorioSaida], summary="Listar laboratórios")
def listar(q: str | None = None, activo: bool | None = None, skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("laboratories", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(Laboratory).where(Laboratory.company_id == company_id)
    if q:
        termo = f"%{q.strip()}%"
        consulta = consulta.where(or_(Laboratory.codigo.ilike(termo), Laboratory.nome.ilike(termo)))
    if activo is not None:
        consulta = consulta.where(Laboratory.activo.is_(activo))
    total, items = paginar(db, consulta.order_by(Laboratory.nome), skip, limit)
    return {"total": total, "items": items}


@router.post("", response_model=LaboratorioSaida, status_code=201, summary="Criar laboratório")
def criar(dados: LaboratorioCriar, ctx: Contexto = Depends(exige("laboratories", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    if db.scalar(select(Laboratory).where(Laboratory.company_id == company_id,
                                          Laboratory.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe um laboratório com este código")
    laboratorio = Laboratory(company_id=company_id, **dados.model_dump())
    db.add(laboratorio)
    db.flush()
    auditar(db, ctx, "criar", "laboratory", laboratorio.id, depois=serializar(laboratorio))
    db.commit()
    return laboratorio


@router.get("/{laboratory_id}", response_model=LaboratorioSaida, summary="Consultar laboratório")
def obter(laboratory_id: str, ctx: Contexto = Depends(exige("laboratories", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), laboratory_id)


@router.patch("/{laboratory_id}", response_model=LaboratorioSaida, summary="Actualizar laboratório")
def actualizar(laboratory_id: str, dados: LaboratorioActualizar,
               ctx: Contexto = Depends(exige("laboratories", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    laboratorio = _obter(db, company_id, laboratory_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "codigo" in alteracoes and alteracoes["codigo"] != laboratorio.codigo:
        if db.scalar(select(Laboratory).where(Laboratory.company_id == company_id,
                                              Laboratory.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe um laboratório com este código")
    antes = serializar(laboratorio)
    for campo, valor in alteracoes.items():
        setattr(laboratorio, campo, valor)
    auditar(db, ctx, "actualizar", "laboratory", laboratorio.id, antes=antes,
            depois=serializar(laboratorio))
    db.commit()
    return laboratorio


@router.delete("/{laboratory_id}", status_code=204, summary="Desactivar laboratório")
def eliminar(laboratory_id: str, ctx: Contexto = Depends(exige("laboratories", "delete")),
             db: Session = Depends(get_db)):
    laboratorio = _obter(db, exigir_empresa(ctx), laboratory_id)
    antes = serializar(laboratorio)
    laboratorio.activo = False
    auditar(db, ctx, "desactivar", "laboratory", laboratorio.id, antes=antes)
    db.commit()
