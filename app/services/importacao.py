"""Importação de CSV/XLSX com pré-visualização, aliases e erros por linha.

A importação é atómica: se existir pelo menos um erro de validação, nada é gravado.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from openpyxl import load_workbook
from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.common import normalizar
from app.deps import Contexto
from app.models import (
    AssayResult, DrillHole, Laboratory, Lithology, Project, Sample, agora,
)
from app.schemas import (
    AmostraCriar, ErroImportacao, FuroCriar, ImportacaoSaida, LitologiaCriar, ResultadoCriar,
)
from app.services.auditoria import auditar
from app.services.coordenadas import completar_coordenadas

ENTIDADES = {
    "sondagens": "drill_holes",
    "sondagem": "drill_holes",
    "furos": "drill_holes",
    "drill_holes": "drill_holes",
    "amostras": "samples",
    "amostra": "samples",
    "samples": "samples",
    "resultados": "assays",
    "resultados_laboratoriais": "assays",
    "analises": "assays",
    "assays": "assays",
    "assay_results": "assays",
    "litologias": "lithologies",
    "litologia": "lithologies",
    "lithologies": "lithologies",
}

ALIASES: dict[str, dict[str, tuple[str, ...]]] = {
    "drill_holes": {
        "projecto": ("projecto", "projeto", "project", "project_code", "codigo_projecto",
                     "codigo do projecto", "projecto_codigo"),
        "codigo": ("codigo", "code", "furo", "hole", "hole_id", "id_furo", "codigo_furo"),
        "nome": ("nome", "name", "designacao"),
        "tipo": ("tipo", "type"),
        "estado": ("estado", "status"),
        "x": ("x", "este", "east"),
        "y": ("y", "norte", "north"),
        "z": ("z", "cota", "elevacao", "elevation"),
        "latitude": ("latitude", "lat"),
        "longitude": ("longitude", "lon", "long"),
        "azimute": ("azimute", "azimuth", "az"),
        "inclinacao": ("inclinacao", "inclination", "dip", "mergulho"),
        "profundidade_prevista": ("profundidade_prevista", "profundidade_planeada",
                                  "planned_depth", "depth_planned"),
        "profundidade_final": ("profundidade_final", "profundidade", "final_depth", "depth"),
        "data_inicio": ("data_inicio", "inicio", "start_date", "data de inicio"),
        "data_fim": ("data_fim", "fim", "end_date", "data de fim"),
        "sonda": ("sonda", "rig"),
        "notas": ("notas", "notes", "observacoes"),
    },
    "samples": {
        "projecto": ("projecto", "projeto", "project", "project_code", "codigo_projecto",
                     "projecto_codigo"),
        "furo": ("furo", "drill_hole", "hole", "hole_code", "codigo_furo", "furo_codigo"),
        "codigo": ("codigo", "code", "amostra", "sample", "sample_id", "id_amostra",
                   "codigo_amostra"),
        "tipo": ("tipo", "type"),
        "de": ("de", "from", "inicio", "start"),
        "ate": ("ate", "to", "fim", "end"),
        "peso_kg": ("peso_kg", "peso", "weight", "weight_kg"),
        "estado": ("estado", "status"),
        "data_recolha": ("data_recolha", "data", "collection_date", "data de recolha"),
        "recolhido_por": ("recolhido_por", "geologo", "collected_by"),
        "notas": ("notas", "notes", "observacoes"),
    },
    "assays": {
        "amostra": ("amostra", "sample", "sample_code", "codigo_amostra"),
        "laboratorio": ("laboratorio", "laboratory", "lab", "lab_code", "codigo_laboratorio"),
        "parametro": ("parametro", "parameter", "elemento", "element", "analise"),
        "valor": ("valor", "value", "resultado", "result", "teor"),
        "unidade": ("unidade", "unit"),
        "metodo": ("metodo", "method"),
        "limite_deteccao": ("limite_deteccao", "detection_limit", "ld"),
        "data_resultado": ("data_resultado", "data", "result_date"),
        "estado": ("estado", "status"),
    },
    "lithologies": {
        "codigo": ("codigo", "code", "litologia", "lithology"),
        "nome": ("nome", "name", "designacao"),
        "descricao": ("descricao", "description", "detalhe"),
        "cor": ("cor", "color", "colour"),
        "activo": ("activo", "ativo", "active"),
    },
}

ROTULOS = {
    "drill_holes": "sondagens",
    "samples": "amostras",
    "assays": "resultados laboratoriais",
    "lithologies": "litologias",
}


def _canonica(entidade: str) -> str:
    chave = normalizar(entidade).replace("-", "_")
    canonica = ENTIDADES.get(chave)
    if canonica is None:
        raise HTTPException(404, f"Entidade de importação desconhecida: {entidade}")
    return canonica


def _ler_csv(conteudo: bytes) -> list[tuple[int, dict[str, Any]]]:
    texto = None
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise HTTPException(422, "Não foi possível descodificar o ficheiro CSV")
    primeira = texto.splitlines()[0] if texto.splitlines() else ""
    delimitador = ","
    if primeira.count(";") > primeira.count(","):
        delimitador = ";"
    elif primeira.count("\t") > primeira.count(",") and primeira.count("\t") > primeira.count(";"):
        delimitador = "\t"
    leitor = csv.reader(io.StringIO(texto), delimiter=delimitador)
    linhas = list(leitor)
    if not linhas:
        return []
    cabecalhos = [normalizar(valor) for valor in linhas[0]]
    resultado: list[tuple[int, dict[str, Any]]] = []
    for numero, linha in enumerate(linhas[1:], start=2):
        if not any(str(valor).strip() for valor in linha):
            continue
        dados = {cabecalho: valor for cabecalho, valor in zip(cabecalhos, linha) if cabecalho}
        resultado.append((numero, dados))
    return resultado


def _ler_xlsx(conteudo: bytes) -> list[tuple[int, dict[str, Any]]]:
    try:
        livro = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - ficheiro inválido é erro do utilizador
        raise HTTPException(422, f"Ficheiro XLSX inválido: {exc}") from exc
    folha = livro.active
    if folha is None:
        raise HTTPException(422, "O ficheiro XLSX não tem folhas")
    iterador = folha.iter_rows(values_only=True)
    try:
        cabecalho = next(iterador)
    except StopIteration:
        return []
    cabecalhos = [normalizar(str(valor)) if valor is not None else "" for valor in cabecalho]
    resultado: list[tuple[int, dict[str, Any]]] = []
    for numero, linha in enumerate(iterador, start=2):
        if linha is None or not any(valor is not None and str(valor).strip() for valor in linha):
            continue
        dados = {cabecalho: valor for cabecalho, valor in zip(cabecalhos, linha) if cabecalho}
        resultado.append((numero, dados))
    livro.close()
    return resultado


def ler_ficheiro(nome: str, conteudo: bytes) -> list[tuple[int, dict[str, Any]]]:
    if not conteudo:
        raise HTTPException(422, "O ficheiro está vazio")
    extensao = nome.rsplit(".", 1)[-1].lower() if "." in nome else ""
    if extensao in ("csv", "txt"):
        return _ler_csv(conteudo)
    if extensao in ("xlsx", "xlsm"):
        return _ler_xlsx(conteudo)
    raise HTTPException(422, "Formato não suportado. Use CSV ou XLSX.")


def _campo(linha: dict[str, Any], entidade: str, campo: str) -> Any:
    for alias in ALIASES[entidade][campo]:
        chave = normalizar(alias)
        if chave in linha:
            valor = linha[chave]
            if isinstance(valor, str) and not valor.strip():
                continue
            return valor
    return None


def _texto(valor: Any) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    texto = str(valor).strip()
    return texto or None


def _obrigatorio(linha: dict[str, Any], entidade: str, campo: str) -> str:
    valor = _texto(_campo(linha, entidade, campo))
    if valor is None:
        raise ValueError(f"O campo '{campo}' é obrigatório")
    return valor


def _num(valor: Any, campo: str) -> float | None:
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = str(valor).strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError as exc:
        raise ValueError(f"O campo '{campo}' tem um valor numérico inválido: {valor}") from exc


def _data(valor: Any, campo: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if not texto:
        return None
    texto = texto.split("T")[0].split(" ")[0]
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"O campo '{campo}' tem uma data inválida: {valor}")


def _booleano(valor: Any) -> bool | None:
    if valor is None:
        return None
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)):
        return bool(valor)
    texto = normalizar(str(valor))
    if not texto:
        return None
    return texto in ("sim", "s", "yes", "y", "true", "1", "verdadeiro", "activo", "ativo")


def _estado(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = normalizar(str(valor)).replace(" ", "_").replace("-", "_")
    return texto or None


def _projecto(db: Session, company_id: str, codigo: str) -> Project | None:
    termo = codigo.strip().lower()
    return db.scalar(select(Project).where(
        Project.company_id == company_id,
        Project.eliminado_em.is_(None),
        or_(func.lower(Project.codigo) == termo, func.lower(Project.nome) == termo),
    ))


def _laboratorio(db: Session, company_id: str, codigo: str) -> Laboratory | None:
    termo = codigo.strip().lower()
    return db.scalar(select(Laboratory).where(
        Laboratory.company_id == company_id,
        or_(func.lower(Laboratory.codigo) == termo, func.lower(Laboratory.nome) == termo),
    ))


def _furo(db: Session, project_id: str, codigo: str) -> DrillHole | None:
    return db.scalar(select(DrillHole).where(
        DrillHole.project_id == project_id, func.lower(DrillHole.codigo) == codigo.strip().lower(),
    ))


def _amostra(db: Session, company_id: str, codigo: str) -> Sample | None:
    return db.scalar(select(Sample).where(
        Sample.company_id == company_id, func.lower(Sample.codigo) == codigo.strip().lower(),
    ))


def _preparar_sondagem(db: Session, company_id: str, linha: dict[str, Any]):
    projecto_codigo = _obrigatorio(linha, "drill_holes", "projecto")
    projeto = _projecto(db, company_id, projecto_codigo)
    if projeto is None:
        raise ValueError(f"Projecto '{projecto_codigo}' não encontrado")
    dados: dict[str, Any] = {
        "project_id": projeto.id,
        "codigo": _obrigatorio(linha, "drill_holes", "codigo"),
    }
    opcionais = {
        "nome": _texto(_campo(linha, "drill_holes", "nome")),
        "tipo": _estado(_campo(linha, "drill_holes", "tipo")),
        "estado": _estado(_campo(linha, "drill_holes", "estado")),
        "x": _num(_campo(linha, "drill_holes", "x"), "x"),
        "y": _num(_campo(linha, "drill_holes", "y"), "y"),
        "z": _num(_campo(linha, "drill_holes", "z"), "z"),
        "latitude": _num(_campo(linha, "drill_holes", "latitude"), "latitude"),
        "longitude": _num(_campo(linha, "drill_holes", "longitude"), "longitude"),
        "azimute": _num(_campo(linha, "drill_holes", "azimute"), "azimute"),
        "inclinacao": _num(_campo(linha, "drill_holes", "inclinacao"), "inclinacao"),
        "profundidade_prevista": _num(
            _campo(linha, "drill_holes", "profundidade_prevista"), "profundidade_prevista"),
        "profundidade_final": _num(
            _campo(linha, "drill_holes", "profundidade_final"), "profundidade_final"),
        "data_inicio": _data(_campo(linha, "drill_holes", "data_inicio"), "data_inicio"),
        "data_fim": _data(_campo(linha, "drill_holes", "data_fim"), "data_fim"),
        "sonda": _texto(_campo(linha, "drill_holes", "sonda")),
        "notas": _texto(_campo(linha, "drill_holes", "notas")),
    }
    dados.update({chave: valor for chave, valor in opcionais.items() if valor is not None})
    modelo = FuroCriar(**dados)
    previa = {
        "projecto": projeto.codigo, "codigo": modelo.codigo, "tipo": modelo.tipo,
        "estado": modelo.estado, "profundidade_final": modelo.profundidade_final,
    }
    return modelo, previa, (projeto.id, modelo.codigo.lower())


def _preparar_amostra(db: Session, company_id: str, linha: dict[str, Any]):
    projecto_codigo = _obrigatorio(linha, "samples", "projecto")
    projeto = _projecto(db, company_id, projecto_codigo)
    if projeto is None:
        raise ValueError(f"Projecto '{projecto_codigo}' não encontrado")
    dados: dict[str, Any] = {
        "project_id": projeto.id,
        "codigo": _obrigatorio(linha, "samples", "codigo"),
    }
    furo_codigo = _texto(_campo(linha, "samples", "furo"))
    if furo_codigo:
        furo = _furo(db, projeto.id, furo_codigo)
        if furo is None:
            raise ValueError(f"Furo '{furo_codigo}' não encontrado no projecto")
        dados["drill_hole_id"] = furo.id
    opcionais = {
        "tipo": _estado(_campo(linha, "samples", "tipo")),
        "de": _num(_campo(linha, "samples", "de"), "de"),
        "ate": _num(_campo(linha, "samples", "ate"), "ate"),
        "peso_kg": _num(_campo(linha, "samples", "peso_kg"), "peso_kg"),
        "estado": _estado(_campo(linha, "samples", "estado")),
        "data_recolha": _data(_campo(linha, "samples", "data_recolha"), "data_recolha"),
        "recolhido_por": _texto(_campo(linha, "samples", "recolhido_por")),
        "notas": _texto(_campo(linha, "samples", "notas")),
    }
    dados.update({chave: valor for chave, valor in opcionais.items() if valor is not None})
    if dados.get("drill_hole_id") and dados.get("ate") is not None:
        furo = db.get(DrillHole, dados["drill_hole_id"])
        if furo and furo.profundidade_final is not None and dados["ate"] > furo.profundidade_final:
            raise ValueError(
                f"A amostra excede a profundidade final do furo ({furo.profundidade_final} m)")
    modelo = AmostraCriar(**dados)
    previa = {
        "projecto": projeto.codigo, "furo": furo_codigo, "codigo": modelo.codigo,
        "de": modelo.de, "ate": modelo.ate, "estado": modelo.estado,
    }
    return modelo, previa, (company_id, modelo.codigo.lower())


def _preparar_resultado(db: Session, company_id: str, linha: dict[str, Any]):
    amostra_codigo = _obrigatorio(linha, "assays", "amostra")
    amostra = _amostra(db, company_id, amostra_codigo)
    if amostra is None:
        raise ValueError(f"Amostra '{amostra_codigo}' não encontrada")
    laboratorio_codigo = _obrigatorio(linha, "assays", "laboratorio")
    laboratorio = _laboratorio(db, company_id, laboratorio_codigo)
    if laboratorio is None:
        raise ValueError(f"Laboratório '{laboratorio_codigo}' não encontrado")
    valor = _num(_campo(linha, "assays", "valor"), "valor")
    if valor is None:
        raise ValueError("O campo 'valor' é obrigatório")
    dados: dict[str, Any] = {
        "sample_id": amostra.id,
        "laboratory_id": laboratorio.id,
        "parametro": _obrigatorio(linha, "assays", "parametro"),
        "valor": valor,
    }
    opcionais = {
        "unidade": _texto(_campo(linha, "assays", "unidade")),
        "metodo": _texto(_campo(linha, "assays", "metodo")),
        "limite_deteccao": _num(_campo(linha, "assays", "limite_deteccao"), "limite_deteccao"),
        "data_resultado": _data(_campo(linha, "assays", "data_resultado"), "data_resultado"),
        "estado": _estado(_campo(linha, "assays", "estado")),
    }
    dados.update({chave: valor for chave, valor in opcionais.items() if valor is not None})
    modelo = ResultadoCriar(**dados)
    previa = {
        "amostra": amostra.codigo, "laboratorio": laboratorio.codigo,
        "parametro": modelo.parametro, "valor": modelo.valor, "unidade": modelo.unidade,
        "estado": modelo.estado,
    }
    chave = (amostra.id, laboratorio.id, modelo.parametro.lower(),
             (modelo.metodo or "").lower())
    return modelo, previa, chave


def _preparar_litologia(db: Session, company_id: str, linha: dict[str, Any]):
    dados: dict[str, Any] = {
        "codigo": _obrigatorio(linha, "lithologies", "codigo"),
        "nome": _obrigatorio(linha, "lithologies", "nome"),
    }
    opcionais = {
        "descricao": _texto(_campo(linha, "lithologies", "descricao")),
        "cor": _texto(_campo(linha, "lithologies", "cor")),
        "activo": _booleano(_campo(linha, "lithologies", "activo")),
    }
    dados.update({chave: valor for chave, valor in opcionais.items() if valor is not None})
    modelo = LitologiaCriar(**dados)
    previa = {"codigo": modelo.codigo, "nome": modelo.nome, "cor": modelo.cor}
    return modelo, previa, (company_id, modelo.codigo.lower())


PREPARADORES = {
    "drill_holes": _preparar_sondagem,
    "samples": _preparar_amostra,
    "assays": _preparar_resultado,
    "lithologies": _preparar_litologia,
}


def _existe_no_bd(db: Session, entidade: str, company_id: str, chave: tuple) -> bool:
    if entidade == "drill_holes":
        project_id, codigo = chave
        return db.scalar(select(DrillHole).where(
            DrillHole.project_id == project_id,
            func.lower(DrillHole.codigo) == codigo).limit(1)) is not None
    if entidade == "samples":
        _, codigo = chave
        return db.scalar(select(Sample).where(
            Sample.company_id == company_id,
            func.lower(Sample.codigo) == codigo).limit(1)) is not None
    if entidade == "lithologies":
        _, codigo = chave
        return db.scalar(select(Lithology).where(
            Lithology.company_id == company_id,
            func.lower(Lithology.codigo) == codigo).limit(1)) is not None
    sample_id, laboratory_id, parametro, metodo = chave
    condicoes = [
        AssayResult.sample_id == sample_id,
        AssayResult.laboratory_id == laboratory_id,
        func.lower(AssayResult.parametro) == parametro,
        func.lower(func.coalesce(AssayResult.metodo, "")) == metodo,
    ]
    return db.scalar(select(AssayResult).where(*condicoes).limit(1)) is not None


def _construir(entidade: str, company_id: str, modelo, ctx: Contexto):
    valores = modelo.model_dump()
    if entidade == "drill_holes":
        return DrillHole(company_id=company_id, **completar_coordenadas(valores))
    if entidade == "samples":
        return Sample(company_id=company_id, **valores)
    if entidade == "lithologies":
        return Lithology(company_id=company_id, **valores)
    estado = valores.pop("estado", "preliminar")
    resultado = AssayResult(company_id=company_id, estado=estado, **valores)
    if estado == "validado":
        resultado.validado_por = ctx.utilizador.id
        resultado.validado_em = agora()
    return resultado


def _mensagem(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        partes = []
        for erro in exc.errors():
            campo = ".".join(str(parte) for parte in erro.get("loc", ()) if parte != "body")
            partes.append(f"{campo}: {erro.get('msg', 'valor inválido')}")
        return "; ".join(partes)
    return str(exc)


def processar(db: Session, ctx: Contexto, entidade: str, nome_ficheiro: str, conteudo: bytes,
              confirmar: bool) -> ImportacaoSaida:
    company_id = ctx.company_id
    if not company_id:
        raise HTTPException(400, "Indique a empresa no cabeçalho X-Company-ID")
    canonica = _canonica(entidade)
    linhas = ler_ficheiro(nome_ficheiro, conteudo)
    if not linhas:
        raise HTTPException(422, "O ficheiro não contém linhas de dados")

    erros: list[ErroImportacao] = []
    itens: list[dict[str, Any]] = []
    chaves: set[tuple] = set()
    for numero, linha in linhas:
        try:
            modelo, previa, chave = PREPARADORES[canonica](db, company_id, linha)
            if canonica == "assays" and modelo.estado == "validado" and not ctx.superadmin \
                    and ("assays", "validate") not in ctx.permissoes:
                raise ValueError("Sem permissão para importar resultados já validados")
            if chave in chaves:
                raise ValueError("Registo duplicado dentro do ficheiro")
            if _existe_no_bd(db, canonica, company_id, chave):
                raise ValueError("Já existe um registo com esta chave na empresa")
            chaves.add(chave)
            itens.append({"linha": numero, "modelo": modelo, "previa": {"linha": numero, **previa}})
        except (ValueError, ValidationError) as exc:
            erros.append(ErroImportacao(linha=numero, mensagem=_mensagem(exc)))
        except HTTPException as exc:
            erros.append(ErroImportacao(linha=numero, mensagem=str(exc.detail)))

    previa = [item["previa"] for item in itens[:10]]
    if erros:
        return ImportacaoSaida(validos=len(itens), criados=0, ignorados=len(erros),
                               previa=previa, erros=erros)
    if not confirmar:
        return ImportacaoSaida(validos=len(itens), criados=0, ignorados=0,
                               previa=previa, erros=[])

    try:
        for item in itens:
            db.add(_construir(canonica, company_id, item["modelo"], ctx))
        db.flush()
        auditar(db, ctx, "importar", canonica, None,
                depois={"ficheiro": nome_ficheiro, "registos": len(itens)})
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        return ImportacaoSaida(
            validos=len(itens), criados=0, ignorados=len(erros), previa=previa,
            erros=[ErroImportacao(linha=0,
                                  mensagem=f"Falha ao gravar os dados ({exc.__class__.__name__})")],
        )
    return ImportacaoSaida(validos=len(itens), criados=len(itens), ignorados=0,
                           previa=previa, erros=[])
