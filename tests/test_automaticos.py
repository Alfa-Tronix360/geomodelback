"""Códigos automáticos (PR-001, FUR-001) e X/Y UTM calculados a partir da latitude/longitude."""
from app.services.coordenadas import geo_para_utm


def test_conversao_utm_pontos_conhecidos():
    x, y, zona, hemisferio = geo_para_utm(40.7484, -73.9857)
    assert (zona, hemisferio) == (18, "N")
    assert abs(x - 585628) < 1 and abs(y - 4511322) < 1
    x, y, zona, hemisferio = geo_para_utm(-8.8383, 13.2344)  # Luanda
    assert (zona, hemisferio) == (33, "S")
    assert 300000 < x < 310000 and 9020000 < y < 9025000


def test_codigo_de_projecto_automatico(cliente, admin_a):
    assert cliente.get("/projects/proximo-codigo", headers=admin_a).json() == {"codigo": "PR-001"}
    p1 = cliente.post("/projects", json={"nome": "Primeiro"}, headers=admin_a)
    assert p1.status_code == 201, p1.text
    assert p1.json()["codigo"] == "PR-001"
    p2 = cliente.post("/projects", json={"nome": "Segundo", "codigo": "  "}, headers=admin_a)
    assert p2.json()["codigo"] == "PR-002"
    manual = cliente.post("/projects", json={"nome": "Manual", "codigo": "KAT-01"}, headers=admin_a)
    assert manual.json()["codigo"] == "KAT-01"
    assert cliente.get("/projects/proximo-codigo", headers=admin_a).json() == {"codigo": "PR-003"}


def test_codigo_de_furo_e_coordenadas_automaticas(cliente, admin_a):
    projecto = cliente.post("/projects", json={"nome": "Furos"}, headers=admin_a).json()
    pid = projecto["id"]
    resposta = cliente.get(f"/drill-holes/proximo-codigo?project_id={pid}", headers=admin_a)
    assert resposta.json() == {"codigo": "FUR-001"}

    furo = cliente.post("/drill-holes", json={
        "project_id": pid, "latitude": -8.8383, "longitude": 13.2344, "z": 50,
    }, headers=admin_a)
    assert furo.status_code == 201, furo.text
    furo = furo.json()
    assert furo["codigo"] == "FUR-001"
    assert abs(furo["x"] - 305821) < 1 and abs(furo["y"] - 9022565) < 1

    # X/Y escritos à mão são respeitados
    manual = cliente.post("/drill-holes", json={
        "project_id": pid, "latitude": -8.8, "longitude": 13.2, "x": 1.0, "y": 2.0,
    }, headers=admin_a).json()
    assert manual["codigo"] == "FUR-002" and (manual["x"], manual["y"]) == (1.0, 2.0)

    # mudar a latitude/longitude recalcula o X/Y
    editado = cliente.patch(f"/drill-holes/{furo['id']}", json={"latitude": -8.9}, headers=admin_a).json()
    assert editado["y"] < furo["y"] and editado["latitude"] == -8.9
