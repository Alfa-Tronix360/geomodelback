"""Aplicação FastAPI do CLACS GeoModel."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import Base, engine
from app.services.arranque import preparar_base_de_dados
from app.services import estados  # noqa: F401  (estados automáticos de furos e projectos)
from app.routers import (
    assays, audit, auth, cena3d, companies, dashboard, drill_holes, importacao, laboratories,
    models3d, projects, resources, samples, users,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.auto_criar_tabelas:
        Base.metadata.create_all(bind=engine)
        preparar_base_de_dados()
    yield


app = FastAPI(
    title=settings.app_nome,
    description=(
        "Backend multiempresa para gestão de dados de geologia mineira: projectos, "
        "sondagens, amostras, resultados laboratoriais, modelação 3D, estimativa de "
        "recursos, dashboard e auditoria."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["http://localhost:5173",
        "https://geomodelfront.vercel.app",],
    # O wildcard é incompatível com credenciais; em desenvolvimento usamos Authorization.
    allow_credentials="*" not in settings.origens,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    auth.router, companies.router, users.router, projects.router, drill_holes.router,
    samples.router, laboratories.router, assays.router, models3d.router, resources.router,
    dashboard.router, audit.router, importacao.router, cena3d.router,
):
    app.include_router(router)


@app.exception_handler(RequestValidationError)
async def validacao_personalizada(_request: Request, exc: RequestValidationError):
    """Mantém os erros de validação legíveis em português."""
    erros = []
    for erro in exc.errors():
        campo = ".".join(str(parte) for parte in erro.get("loc", ()) if parte != "body")
        erros.append({"campo": campo or "corpo", "mensagem": erro.get("msg", "valor inválido")})
    return JSONResponse(status_code=422, content={"detail": erros})


@app.get("/", tags=["Sistema"], summary="Identificação do serviço")
def raiz():
    return {
        "servico": settings.app_nome,
        "versao": "1.0.0",
        "documentacao": "/docs",
        "estado": "operacional",
    }


@app.get("/health", tags=["Sistema"], summary="Verificação de saúde")
def saude():
    return {"estado": "ok"}
