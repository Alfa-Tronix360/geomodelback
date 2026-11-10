"""Importação CSV/XLSX com pré-visualização e atomicidade."""
from __future__ import annotations

from io import BytesIO

from openpyxl import Workbook


def _csv(conteudo: str) -> bytes:
    return conteudo.encode("utf-8")


def test_importacao_csv_preview_e_confirmacao(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    conteudo = _csv(
        "projecto;codigo;profundidade_final;x;y;z\n"
        "PRJ-001;F-IMP-1;100;10;20;30\n"
        "PRJ-001;F-IMP-2;120;15;25;35\n"
    )
    ficheiro = {"ficheiro": ("sondagens.csv", conteudo, "text/csv")}

    resposta = cliente.post("/imports/preview/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    previa = resposta.json()
    assert previa["validos"] == 2
    assert previa["criados"] == 0
    assert len(previa["previa"]) == 2
    assert previa["erros"] == []

    resposta = cliente.post("/imports/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    resultado = resposta.json()
    assert resultado["criados"] == 2
    assert resultado["erros"] == []

    resposta = cliente.get(f"/drill-holes?project_id={projeto['id']}", headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 2

    resposta = cliente.post("/imports/preview/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.json()["validos"] == 0
    assert len(resposta.json()["erros"]) == 2


def test_importacao_invalida_nao_grava_nada(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    conteudo = _csv(
        "projecto;codigo;profundidade_final\n"
        "PRJ-001;F-BOM;100\n"
        "PRJ-001;F-MAU;abc\n"
    )
    ficheiro = {"ficheiro": ("sondagens.csv", conteudo, "text/csv")}

    resposta = cliente.post("/imports/preview/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["validos"] == 1
    assert dados["ignorados"] == 1
    assert dados["erros"][0]["linha"] == 3

    resposta = cliente.post("/imports/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.json()["criados"] == 0

    resposta = cliente.get(f"/drill-holes?project_id={projeto['id']}", headers=admin_a)
    assert resposta.json()["total"] == 0


def test_importacao_xlsx_de_litologias(cliente, admin_a):
    livro = Workbook()
    folha = livro.active
    folha.append(["codigo", "nome", "cor", "activo"])
    folha.append(["LIT-1", "Arenito", "#ffff00", "sim"])
    folha.append(["LIT-2", "Argilito", "#00ffff", "não"])
    buffer = BytesIO()
    livro.save(buffer)
    ficheiro = {
        "ficheiro": (
            "litologias.xlsx", buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    resposta = cliente.post("/imports/preview/litologias", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["validos"] == 2

    resposta = cliente.post("/imports/litologias", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["criados"] == 2

    resposta = cliente.get("/lithologies", headers=admin_a)
    assert resposta.status_code == 200
    codigos = {item["codigo"]: item for item in resposta.json()}
    assert codigos["LIT-1"]["activo"] is True
    assert codigos["LIT-2"]["activo"] is False


def test_importacao_formato_nao_suportado(cliente, admin_a):
    ficheiro = {"ficheiro": ("dados.pdf", b"%PDF-1.4", "application/pdf")}
    resposta = cliente.post("/imports/preview/sondagens", files=ficheiro, headers=admin_a)
    assert resposta.status_code == 422
