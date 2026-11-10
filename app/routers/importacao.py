"""Importação de dados geológicos a partir de CSV ou XLSX."""
from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import Contexto, exige
from app.schemas import ImportacaoSaida
from app.services.importacao import ALIASES, ROTULOS, processar

router = APIRouter(prefix="/imports", tags=["Importação"])


@router.get("/entities", summary="Entidades e campos suportados na importação")
def entidades(ctx: Contexto = Depends(exige("imports", "view"))):
    vistos: set[str] = set()
    resultado = []
    for canonica in ("drill_holes", "samples", "assays", "lithologies"):
        if canonica in vistos:
            continue
        vistos.add(canonica)
        resultado.append({
            "entidade": canonica,
            "rotulo": ROTULOS[canonica],
            "campos": list(ALIASES[canonica].keys()),
            "aliases": {campo: list(aliases) for campo, aliases in ALIASES[canonica].items()},
            "formatos": ["csv", "xlsx"],
        })
    return resultado


@router.post("/preview/{entidade}", response_model=ImportacaoSaida,
             summary="Pré-visualizar importação sem gravar")
async def previa(entidade: str, ficheiro: UploadFile = File(...),
                 ctx: Contexto = Depends(exige("imports", "view")),
                 db: Session = Depends(get_db)):
    conteudo = await ficheiro.read()
    return processar(db, ctx, entidade, ficheiro.filename or "dados.csv", conteudo,
                     confirmar=False)


@router.post("/{entidade}", response_model=ImportacaoSaida,
             summary="Importar e gravar dados")
async def importar(entidade: str, ficheiro: UploadFile = File(...),
                   ctx: Contexto = Depends(exige("imports", "import")),
                   db: Session = Depends(get_db)):
    conteudo = await ficheiro.read()
    return processar(db, ctx, entidade, ficheiro.filename or "dados.csv", conteudo,
                     confirmar=True)
