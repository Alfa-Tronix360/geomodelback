"""Estados automáticos de furos e projectos."""
from datetime import date, timedelta


def _estado_projecto(cliente, pid, cab):
    return cliente.get(f"/projects/{pid}", headers=cab).json()["estado"]


def test_estados_automaticos_do_furo_e_do_projecto(cliente, admin_a):
    pid = cliente.post("/projects", json={"nome": "Projecto Auto", "estado": "activo"}, headers=admin_a).json()["id"]
    assert _estado_projecto(cliente, pid, admin_a) == "planeado"  # sem dados: o estado enviado é ignorado

    furo = cliente.post("/drill-holes", json={"project_id": pid, "x": 0, "y": 0, "z": 100,
                                              "profundidade_prevista": 200, "estado": "concluido"},
                        headers=admin_a).json()
    assert furo["estado"] == "planeado"
    assert _estado_projecto(cliente, pid, admin_a) == "planeado"

    # o primeiro survey põe o furo em sondagem e o projecto activo
    r = cliente.post(f"/drill-holes/{furo['id']}/surveys",
                     json={"profundidade": 0, "azimute": 90, "inclinacao": -60}, headers=admin_a)
    assert r.status_code == 201, r.text
    assert cliente.get(f"/drill-holes/{furo['id']}", headers=admin_a).json()["estado"] == "em_sondagem"
    assert _estado_projecto(cliente, pid, admin_a) == "activo"

    # data de fim → concluído
    r = cliente.patch(f"/drill-holes/{furo['id']}", json={"data_inicio": "2026-10-01", "data_fim": "2026-10-20",
                                                          "profundidade_final": 180}, headers=admin_a)
    assert r.json()["estado"] == "concluido"

    # abandonado é manual e mantém-se; voltar a um estado automático recalcula
    assert cliente.patch(f"/drill-holes/{furo['id']}", json={"estado": "abandonado"},
                         headers=admin_a).json()["estado"] == "abandonado"
    assert cliente.patch(f"/drill-holes/{furo['id']}", json={"notas": "x"},
                         headers=admin_a).json()["estado"] == "abandonado"
    assert cliente.patch(f"/drill-holes/{furo['id']}", json={"estado": "planeado"},
                         headers=admin_a).json()["estado"] == "concluido"

    # suspenso é manual; data de fim passada → encerrado
    assert cliente.patch(f"/projects/{pid}", json={"estado": "suspenso"}, headers=admin_a).json()["estado"] == "suspenso"
    assert cliente.patch(f"/projects/{pid}", json={"estado": "planeado"}, headers=admin_a).json()["estado"] == "activo"
    ontem = (date.today() - timedelta(days=1)).isoformat()
    r = cliente.patch(f"/projects/{pid}", json={"data_inicio": "2026-01-01", "data_fim": ontem}, headers=admin_a)
    assert r.json()["estado"] == "encerrado"


def test_projecto_com_data_de_inicio_futura_fica_planeado(cliente, admin_a):
    amanha = (date.today() + timedelta(days=1)).isoformat()
    p = cliente.post("/projects", json={"nome": "Futuro", "data_inicio": amanha}, headers=admin_a).json()
    assert p["estado"] == "planeado"
    hoje = date.today().isoformat()
    assert cliente.patch(f"/projects/{p['id']}", json={"data_inicio": hoje}, headers=admin_a).json()["estado"] == "activo"
