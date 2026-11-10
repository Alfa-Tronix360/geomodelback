"""Projectos mineiros, áreas e litologias."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.common import paginar
from app.database import get_db
from app.deps import Contexto, exige, exigir_empresa
from app.models import CompanyUser, Lithology, Project, ProjectArea, User, agora
from app.schemas import (
    AreaProjectoActualizar, AreaProjetoCriar, AreaProjectoSaida, LitologiaActualizar, LitologiaCriar,
    LitologiaSaida, Pagina, ProjectoActualizar, ProjectoCriar, ProjectoSaida,
)
from app.services.auditoria import auditar, serializar
from app.services.geo import validar_geojson
from app.services.codigos import proximo_codigo_projecto

router = APIRouter(tags=["Projectos e litologias"])


def _obter(db: Session, company_id: str, project_id: str, incluir_eliminados: bool = False) -> Project:
    projeto = db.get(Project, project_id)
    if projeto is None or projeto.company_id != company_id:
        raise HTTPException(404, "Projecto não encontrado")
    if projeto.eliminado_em is not None and not incluir_eliminados:
        raise HTTPException(404, "Projecto não encontrado")
    return projeto


def _obter_area(db: Session, company_id: str, project_id: str, area_id: str) -> ProjectArea:
    area = db.get(ProjectArea, area_id)
    if area is None or area.company_id != company_id or area.project_id != project_id:
        raise HTTPException(404, "Área não encontrada")
    return area


def _validar_gestor(db: Session, company_id: str, gestor_id: str | None) -> None:
    if not gestor_id:
        return
    utilizador = db.get(User, gestor_id)
    membro = db.scalar(select(CompanyUser).where(
        CompanyUser.company_id == company_id, CompanyUser.user_id == gestor_id))
    if utilizador is None or membro is None:
        raise HTTPException(422, "O gestor indicado não pertence à empresa")


@router.get("/projects", response_model=Pagina[ProjectoSaida], summary="Listar projectos")
def listar(estado: str | None = None, mineral: str | None = None, q: str | None = None,
           incluir_eliminados: bool = False, skip: int = 0, limit: int = 50,
           ctx: Contexto = Depends(exige("projects", "view")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(Project).where(Project.company_id == company_id)
    if not incluir_eliminados:
        consulta = consulta.where(Project.eliminado_em.is_(None))
    if estado:
        consulta = consulta.where(Project.estado == estado)
    if mineral:
        consulta = consulta.where(Project.mineral == mineral)
    if q:
        termo = f"%{q.strip()}%"
        consulta = consulta.where(or_(Project.nome.ilike(termo), Project.codigo.ilike(termo)))
    consulta = consulta.order_by(Project.nome)
    total, items = paginar(db, consulta, skip, limit)
    return {"total": total, "items": items}


@router.get("/projects/proximo-codigo", summary="Próximo código automático de projecto")
def proximo_codigo(ctx: Contexto = Depends(exige("projects", "create")), db: Session = Depends(get_db)):
    return {"codigo": proximo_codigo_projecto(db, exigir_empresa(ctx))}


@router.post("/projects", response_model=ProjectoSaida, status_code=201, summary="Criar projecto")
def criar(dados: ProjectoCriar, ctx: Contexto = Depends(exige("projects", "create")),
          db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    dados.codigo = (dados.codigo or "").strip() or proximo_codigo_projecto(db, company_id)
    if db.scalar(select(Project).where(Project.company_id == company_id, Project.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe um projecto com este código")
    _validar_gestor(db, company_id, dados.gestor_id)
    validar_geojson(dados.geometria)
    projeto = Project(company_id=company_id, **dados.model_dump())
    db.add(projeto)
    db.flush()
    auditar(db, ctx, "criar", "project", projeto.id, depois=serializar(projeto))
    db.commit()
    return projeto


@router.get("/projects/{project_id}", response_model=ProjectoSaida, summary="Consultar projecto")
def obter(project_id: str, ctx: Contexto = Depends(exige("projects", "view")),
          db: Session = Depends(get_db)):
    return _obter(db, exigir_empresa(ctx), project_id)


@router.patch("/projects/{project_id}", response_model=ProjectoSaida, summary="Actualizar projecto")
def actualizar(project_id: str, dados: ProjectoActualizar,
               ctx: Contexto = Depends(exige("projects", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    projeto = _obter(db, company_id, project_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "codigo" in alteracoes and alteracoes["codigo"] != projeto.codigo:
        if db.scalar(select(Project).where(Project.company_id == company_id,
                                           Project.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe um projecto com este código")
    if "gestor_id" in alteracoes:
        _validar_gestor(db, company_id, alteracoes["gestor_id"])
    if "geometria" in alteracoes:
        validar_geojson(alteracoes["geometria"])
    inicio = alteracoes.get("data_inicio", projeto.data_inicio)
    fim = alteracoes.get("data_fim", projeto.data_fim)
    if inicio and fim and fim < inicio:
        raise HTTPException(422, "data_fim não pode ser anterior a data_inicio")
    antes = serializar(projeto)
    for campo, valor in alteracoes.items():
        setattr(projeto, campo, valor)
    auditar(db, ctx, "actualizar", "project", projeto.id, antes=antes, depois=serializar(projeto))
    db.commit()
    return projeto


@router.delete("/projects/{project_id}", status_code=204, summary="Eliminar projecto (soft delete)")
def eliminar(project_id: str, ctx: Contexto = Depends(exige("projects", "delete")),
             db: Session = Depends(get_db)):
    projeto = _obter(db, exigir_empresa(ctx), project_id)
    antes = serializar(projeto)
    projeto.eliminado_em = agora()
    auditar(db, ctx, "eliminar", "project", projeto.id, antes=antes)
    db.commit()


@router.get("/projects/{project_id}/areas", response_model=list[AreaProjectoSaida],
            summary="Áreas do projecto")
def listar_areas(project_id: str, ctx: Contexto = Depends(exige("projects", "view")),
                 db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, project_id)
    return list(db.scalars(select(ProjectArea).where(
        ProjectArea.company_id == company_id, ProjectArea.project_id == project_id).order_by(ProjectArea.nome)))


@router.post("/projects/{project_id}/areas", response_model=AreaProjectoSaida, status_code=201,
             summary="Criar área do projecto")
def criar_area(project_id: str, dados: AreaProjetoCriar,
               ctx: Contexto = Depends(exige("projects", "create")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, project_id)
    validar_geojson(dados.geometria)
    area = ProjectArea(company_id=company_id, project_id=project_id, **dados.model_dump())
    db.add(area)
    db.flush()
    auditar(db, ctx, "criar", "project_area", area.id, depois=serializar(area))
    db.commit()
    return area


@router.patch("/projects/{project_id}/areas/{area_id}", response_model=AreaProjectoSaida,
              summary="Actualizar área")
def actualizar_area(project_id: str, area_id: str, dados: AreaProjectoActualizar,
                    ctx: Contexto = Depends(exige("projects", "edit")), db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, project_id)
    area = _obter_area(db, company_id, project_id, area_id)
    alteracoes = dados.model_dump(exclude_unset=True)
    if "geometria" in alteracoes:
        validar_geojson(alteracoes["geometria"])
    antes = serializar(area)
    for campo, valor in alteracoes.items():
        setattr(area, campo, valor)
    auditar(db, ctx, "actualizar", "project_area", area.id, antes=antes, depois=serializar(area))
    db.commit()
    return area


@router.delete("/projects/{project_id}/areas/{area_id}", status_code=204, summary="Eliminar área")
def eliminar_area(project_id: str, area_id: str, ctx: Contexto = Depends(exige("projects", "delete")),
                  db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    _obter(db, company_id, project_id)
    area = _obter_area(db, company_id, project_id, area_id)
    auditar(db, ctx, "eliminar", "project_area", area.id, antes=serializar(area))
    db.delete(area)
    db.commit()


# ---------------------------------------------------------------- litologias
@router.get("/lithologies", response_model=list[LitologiaSaida], summary="Listar litologias")
def listar_litologias(activo: bool | None = None, ctx: Contexto = Depends(exige("projects", "view")),
                      db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    consulta = select(Lithology).where(Lithology.company_id == company_id)
    if activo is not None:
        consulta = consulta.where(Lithology.activo.is_(activo))
    return list(db.scalars(consulta.order_by(Lithology.nome)))


@router.post("/lithologies", response_model=LitologiaSaida, status_code=201, summary="Criar litologia")
def criar_litologia(dados: LitologiaCriar, ctx: Contexto = Depends(exige("projects", "create")),
                    db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    if db.scalar(select(Lithology).where(Lithology.company_id == company_id,
                                         Lithology.codigo == dados.codigo)):
        raise HTTPException(409, "Já existe uma litologia com este código")
    litologia = Lithology(company_id=company_id, **dados.model_dump())
    db.add(litologia)
    db.flush()
    auditar(db, ctx, "criar", "lithology", litologia.id, depois=serializar(litologia))
    db.commit()
    return litologia


@router.patch("/lithologies/{lithology_id}", response_model=LitologiaSaida, summary="Actualizar litologia")
def actualizar_litologia(lithology_id: str, dados: LitologiaActualizar,
                         ctx: Contexto = Depends(exige("projects", "edit")),
                         db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    litologia = db.get(Lithology, lithology_id)
    if litologia is None or litologia.company_id != company_id:
        raise HTTPException(404, "Litologia não encontrada")
    alteracoes = dados.model_dump(exclude_unset=True)
    if "codigo" in alteracoes and alteracoes["codigo"] != litologia.codigo:
        if db.scalar(select(Lithology).where(Lithology.company_id == company_id,
                                             Lithology.codigo == alteracoes["codigo"])):
            raise HTTPException(409, "Já existe uma litologia com este código")
    antes = serializar(litologia)
    for campo, valor in alteracoes.items():
        setattr(litologia, campo, valor)
    auditar(db, ctx, "actualizar", "lithology", litologia.id, antes=antes, depois=serializar(litologia))
    db.commit()
    return litologia


@router.delete("/lithologies/{lithology_id}", status_code=204, summary="Eliminar litologia")
def eliminar_litologia(lithology_id: str, ctx: Contexto = Depends(exige("projects", "delete")),
                       db: Session = Depends(get_db)):
    company_id = exigir_empresa(ctx)
    litologia = db.get(Lithology, lithology_id)
    if litologia is None or litologia.company_id != company_id:
        raise HTTPException(404, "Litologia não encontrada")
    auditar(db, ctx, "eliminar", "lithology", litologia.id, antes=serializar(litologia))
    db.delete(litologia)
    db.commit()
