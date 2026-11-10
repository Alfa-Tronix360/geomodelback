"""Modelação 3D, domínios, versões e estimativa de recursos."""
from __future__ import annotations


def test_modelos_dominios_e_versoes(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    resposta = cliente.post(
        "/models", json={"project_id": projeto["id"], "nome": "Modelo 1"}, headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    modelo = resposta.json()
    assert modelo["versao_actual"] == 0

    resposta = cliente.post(
        f"/models/{modelo['id']}/domains",
        json={"codigo": "DOM-1", "nome": "Domínio principal", "cor": "#ff0000"},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.post(
        f"/models/{modelo['id']}/domains",
        json={"codigo": "DOM-1", "nome": "Duplicado"},
        headers=admin_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.post(
        f"/models/{modelo['id']}/versions", json={"nome": "Versão 1"}, headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    versao_1 = resposta.json()
    assert versao_1["numero_versao"] == 1

    resposta = cliente.post(
        f"/models/{modelo['id']}/versions", json={"nome": "Versão 2"}, headers=admin_a,
    )
    assert resposta.status_code == 201
    versao_2 = resposta.json()
    assert versao_2["numero_versao"] == 2

    resposta = cliente.get(f"/models/{modelo['id']}", headers=admin_a)
    assert resposta.json()["versao_actual"] == 2

    resposta = cliente.post(
        f"/models/{modelo['id']}/versions/{versao_2['id']}/validate", headers=admin_a,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["estado"] == "validado"
    assert resposta.json()["validado_por"] is not None

    resposta = cliente.get(f"/models/{modelo['id']}", headers=admin_a)
    assert resposta.json()["estado"] == "validado"

    resposta = cliente.delete(
        f"/models/{modelo['id']}/versions/{versao_2['id']}", headers=admin_a,
    )
    assert resposta.status_code == 409


def test_estimativa_calcula_tonelagem_e_metal(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    resposta = cliente.post(
        "/resources",
        json={
            "project_id": projeto["id"], "nome": "Estimativa inicial", "commodity": "Cu",
            "volume_m3": 1000, "densidade": 2.5, "teor_corte": 1.5, "unidade_teor": "%",
        },
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    estimativa = resposta.json()
    assert estimativa["tonelagem"] == 2500.0
    assert estimativa["metal_contido"] == 37.5

    resposta = cliente.patch(
        f"/resources/{estimativa['id']}", json={"volume_m3": 2000}, headers=admin_a,
    )
    assert resposta.status_code == 200, resposta.text
    actualizada = resposta.json()
    assert actualizada["tonelagem"] == 5000.0
    assert actualizada["metal_contido"] == 75.0

    resposta = cliente.post(f"/resources/{estimativa['id']}/validate", headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.json()["estado"] == "validado"
    assert resposta.json()["validado_por"] is not None


def test_estimativa_rejeita_modelo_de_outro_projecto(cliente, criar_projecto, admin_a):
    projeto_a = criar_projecto()
    projeto_b = criar_projecto(codigo="PRJ-002", nome="Projecto B")
    resposta = cliente.post(
        "/models", json={"project_id": projeto_b["id"], "nome": "Modelo B"}, headers=admin_a,
    )
    assert resposta.status_code == 201
    modelo_b = resposta.json()

    resposta = cliente.post(
        "/resources",
        json={
            "project_id": projeto_a["id"], "model_id": modelo_b["id"], "nome": "Inválida",
            "commodity": "Au", "volume_m3": 100, "densidade": 2.5,
        },
        headers=admin_a,
    )
    assert resposta.status_code == 422
