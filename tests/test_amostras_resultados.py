"""Amostras, laboratórios e resultados laboratoriais."""
from __future__ import annotations


def test_amostras_intervalos_e_resultados(cliente, criar_projecto, criar_furo, criar_laboratorio,
                                          admin_a, lab_a, geologo_a):
    projeto = criar_projecto()
    furo = criar_furo(projeto["id"], "F-001")
    laboratorio = criar_laboratorio()

    resposta = cliente.post(
        f"/drill-holes/{furo['id']}/intervals", json={"de": 0, "ate": 20}, headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    intervalo = resposta.json()

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"],
              "drill_interval_id": intervalo["id"], "codigo": "AM-1", "de": 5, "ate": 15,
              "peso_kg": 4.5},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    amostra = resposta.json()
    assert amostra["drill_hole_id"] == furo["id"]

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"],
              "drill_interval_id": intervalo["id"], "codigo": "AM-2", "de": 15, "ate": 25},
        headers=admin_a,
    )
    assert resposta.status_code == 422

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"], "codigo": "AM-3",
              "de": 140, "ate": 160},
        headers=admin_a,
    )
    assert resposta.status_code == 422

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"], "codigo": "AM-1",
              "de": 10, "ate": 12},
        headers=admin_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.post(
        "/assays",
        json={"sample_id": amostra["id"], "laboratory_id": laboratorio["id"],
              "parametro": "Cu", "valor": 1.2, "unidade": "%", "metodo": "ICP-OES"},
        headers=lab_a,
    )
    assert resposta.status_code == 201, resposta.text
    resultado = resposta.json()
    assert resultado["estado"] == "preliminar"
    assert resultado["validado_por"] is None

    resposta = cliente.post(
        "/assays",
        json={"sample_id": amostra["id"], "laboratory_id": laboratorio["id"],
              "parametro": "Cu", "valor": 1.3, "unidade": "%", "metodo": "ICP-OES"},
        headers=lab_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.post(f"/assays/{resultado['id']}/validate", headers=geologo_a)
    assert resposta.status_code == 403

    resposta = cliente.post(f"/assays/{resultado['id']}/validate", headers=lab_a)
    assert resposta.status_code == 200, resposta.text
    validado = resposta.json()
    assert validado["estado"] == "validado"
    assert validado["validado_por"] is not None
    assert validado["validado_em"] is not None

    resposta = cliente.patch(
        f"/assays/{resultado['id']}", json={"estado": "preliminar"}, headers=lab_a,
    )
    assert resposta.status_code == 200
    assert resposta.json()["validado_por"] is None


def test_laboratorio_inactivo_nao_aceita_resultados(cliente, criar_projecto, criar_furo,
                                                     criar_laboratorio, admin_a, lab_a):
    projeto = criar_projecto()
    furo = criar_furo(projeto["id"])
    laboratorio = criar_laboratorio()
    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"], "codigo": "AM-X"},
        headers=admin_a,
    )
    assert resposta.status_code == 201
    amostra = resposta.json()

    resposta = cliente.delete(f"/laboratories/{laboratorio['id']}", headers=admin_a)
    assert resposta.status_code == 204

    resposta = cliente.post(
        "/assays",
        json={"sample_id": amostra["id"], "laboratory_id": laboratorio["id"],
              "parametro": "Au", "valor": 0.5, "unidade": "ppm"},
        headers=lab_a,
    )
    assert resposta.status_code == 422
