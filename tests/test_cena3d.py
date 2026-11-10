"""Cena 3D do projecto: geometria, intervalos e isolamento entre empresas."""


def test_cena3d_do_projecto(cliente, criar_projecto, criar_furo, admin_a, admin_b):
    projecto = criar_projecto()
    furo = criar_furo(projecto["id"])
    criar_furo(projecto["id"], codigo="F-SEM", x=None, y=None, z=None)
    base = f"/drill-holes/{furo['id']}"
    assert cliente.post(f"{base}/surveys", json={"profundidade": 50, "azimute": 90, "inclinacao": -60},
                        headers=admin_a).status_code == 201
    assert cliente.post(f"{base}/intervals", json={"de": 0, "ate": 40}, headers=admin_a).status_code == 201

    resposta = cliente.get(f"/projects/{projecto['id']}/scene-3d", headers=admin_a)
    assert resposta.status_code == 200, resposta.text
    cena = resposta.json()
    assert cena["sem_coordenadas"] == ["F-SEM"]
    assert len(cena["furos"]) == 1
    dados = cena["furos"][0]
    assert dados["profundidade"] == 150
    assert dados["pontos"][0] == {"profundidade": 0.0, "x": 0.0, "y": 0.0, "z": 100.0}
    # a trajectória é prolongada até à profundidade final, a descer para Este
    final = dados["pontos"][-1]
    assert final["profundidade"] == 150
    assert final["x"] > 70 and final["z"] < 0
    assert dados["intervalos"][0]["de"] == 0 and dados["intervalos"][0]["ate"] == 40

    # outra empresa não vê a cena
    assert cliente.get(f"/projects/{projecto['id']}/scene-3d", headers=admin_b).status_code == 404
