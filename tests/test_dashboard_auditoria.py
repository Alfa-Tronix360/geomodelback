"""Indicadores do dashboard e registo de auditoria."""
from __future__ import annotations


def test_dashboard_e_auditoria(cliente, criar_projecto, criar_furo, criar_laboratorio,
                               admin_a, lab_a):
    projeto = criar_projecto(area_km2=25.0)
    furo = criar_furo(projeto["id"], "F-001")
    laboratorio = criar_laboratorio()

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"], "codigo": "AM-1",
              "de": 10, "ate": 12},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    amostra = resposta.json()

    resposta = cliente.post(
        "/assays",
        json={"sample_id": amostra["id"], "laboratory_id": laboratorio["id"],
              "parametro": "Cu", "valor": 1.2, "unidade": "%"},
        headers=lab_a,
    )
    assert resposta.status_code == 201, resposta.text
    resultado = resposta.json()
    resposta = cliente.post(f"/assays/{resultado['id']}/validate", headers=lab_a)
    assert resposta.status_code == 200

    resposta = cliente.post(
        "/models", json={"project_id": projeto["id"], "nome": "Modelo Dashboard"}, headers=admin_a,
    )
    assert resposta.status_code == 201

    resposta = cliente.post(
        "/resources",
        json={
            "project_id": projeto["id"], "nome": "Estimativa Dashboard", "commodity": "Cu",
            "volume_m3": 1000, "densidade": 2.5, "teor_corte": 1.5, "unidade_teor": "%",
            "estado": "validado",
        },
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.get("/dashboard", headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    dados = resposta.json()
    assert dados["projectos_activos"] == 1
    assert dados["area_explorada_km2"] == 25.0
    assert dados["sondagens"] == 1
    assert dados["metros_perfurados"] == 150.0
    assert dados["amostras"] == 1
    assert dados["resultados_laboratoriais"] == 1
    assert dados["resultados_validados"] == 1
    assert dados["modelos_geologicos"] == 1
    assert dados["estimativas"] == 1
    assert dados["tonelagem_total"] == 2500.0
    assert dados["metal_contido_total"] == 37.5
    assert dados["por_estado_sondagem"]["concluido"] == 1
    assert dados["por_mineral"][0]["mineral"] == "Cobre"

    resposta = cliente.get("/audit", headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["total"] >= 1

    resposta = cliente.get("/audit?entidade=project", headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.json()["total"] >= 1
    assert resposta.json()["items"][0]["accao"] == "criar"

    resposta = cliente.get("/audit/export", headers=admin_a)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert "project" in resposta.text
