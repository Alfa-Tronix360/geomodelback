"""Validação de sondagens, surveys, intervalos e trajectória 3D."""
from __future__ import annotations


def test_sondagem_surveys_intervalos_e_trajectoria(cliente, criar_projecto, criar_furo, admin_a):
    projeto = criar_projecto()
    furo = criar_furo(projeto["id"], "F-001")
    base = f"/drill-holes/{furo['id']}"

    resposta = cliente.post(
        f"{base}/surveys",
        json={"profundidade": 0, "azimute": 90, "inclinacao": -60},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.post(
        f"{base}/surveys",
        json={"profundidade": 0, "azimute": 90, "inclinacao": -60},
        headers=admin_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.post(
        f"{base}/surveys",
        json={"profundidade": 200, "azimute": 90, "inclinacao": -60},
        headers=admin_a,
    )
    assert resposta.status_code == 422

    resposta = cliente.post(
        f"{base}/surveys",
        json={"profundidade": 50, "azimute": 91, "inclinacao": -61},
        headers=admin_a,
    )
    assert resposta.status_code == 201

    resposta = cliente.get(f"{base}/trajectory", headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    trajectoria = resposta.json()
    assert trajectoria["comprimento"] == 50.0
    assert len(trajectoria["pontos"]) == 3
    assert trajectoria["pontos"][-1]["profundidade"] == 50.0

    resposta = cliente.post(
        f"{base}/intervals", json={"de": 0, "ate": 20}, headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.post(
        f"{base}/intervals", json={"de": 15, "ate": 30}, headers=admin_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.post(
        f"{base}/intervals", json={"de": 20, "ate": 40}, headers=admin_a,
    )
    assert resposta.status_code == 201

    resposta = cliente.post(
        f"{base}/intervals", json={"de": 140, "ate": 160}, headers=admin_a,
    )
    assert resposta.status_code == 422

    resposta = cliente.patch(f"{base}", json={"profundidade_final": 30}, headers=admin_a)
    assert resposta.status_code == 422

    resposta = cliente.patch(f"{base}", json={"profundidade_final": 180}, headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["profundidade_final"] == 180.0

    resposta = cliente.patch(
        f"{base}", json={"profundidade_prevista": 100, "profundidade_final": 150},
        headers=admin_a,
    )
    assert resposta.status_code == 422


def test_furo_com_coordenadas_geograficas_invalidas(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    resposta = cliente.post(
        "/drill-holes",
        json={"project_id": projeto["id"], "codigo": "F-LAT", "latitude": 100, "longitude": 20},
        headers=admin_a,
    )
    assert resposta.status_code == 422
