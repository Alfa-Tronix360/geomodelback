"""Sino: avisa quem tem de agir no passo seguinte do fluxo."""


def _sino(cliente, cab):
    r = cliente.get("/notifications", headers=cab)
    assert r.status_code == 200, r.text
    return r.json()


def test_fluxo_notifica_o_passo_seguinte(cliente, criar_projecto, criar_furo, criar_laboratorio,
                                         admin_a, geologo_a, lab_a):
    projecto = criar_projecto()
    furo = criar_furo(projecto["id"])  # tem data de fim → concluído → avisa quem regista amostras
    assert any(n["tipo"] == "furo_concluido" for n in _sino(cliente, geologo_a)["items"])
    assert not any(n["tipo"] == "furo_concluido" for n in _sino(cliente, lab_a)["items"])  # lab não regista amostras

    lab = criar_laboratorio()
    # o geólogo envia a amostra ao laboratório → o técnico de laboratório é avisado; o geólogo (autor) não
    amostra = cliente.post("/samples", json={"project_id": projecto["id"], "drill_hole_id": furo["id"],
                                             "codigo": "AM-001", "de": 10, "ate": 11, "estado": "enviada"},
                           headers=geologo_a)
    assert amostra.status_code == 201, amostra.text
    sino_lab = _sino(cliente, lab_a)
    assert sino_lab["nao_lidas"] >= 1
    assert sino_lab["items"][0]["tipo"] == "amostra_enviada"
    assert not any(n["tipo"] == "amostra_enviada" for n in _sino(cliente, geologo_a)["items"])

    # o laboratório lança dois resultados → quem valida recebe UM aviso agrupado (admin; o lab é o autor)
    for parametro in ("Cu", "Au"):
        r = cliente.post("/assays", json={"sample_id": amostra.json()["id"], "laboratory_id": lab["id"],
                                          "parametro": parametro, "valor": 1.2, "unidade": "%", "metodo": "ICP"},
                         headers=lab_a)
        assert r.status_code == 201, r.text
    avisos = [n for n in _sino(cliente, admin_a)["items"] if n["tipo"] == "resultado_por_validar"]
    assert len(avisos) == 1 and "2 resultado" in avisos[0]["mensagem"]

    # validar → o geólogo (models:create) é avisado
    cliente.post(f"/assays/{r.json()['id']}/validate", headers=admin_a)
    assert any(n["tipo"] == "resultado_validado" for n in _sino(cliente, geologo_a)["items"])

    # marcar como lida / todas
    sino = _sino(cliente, admin_a)
    nid = sino["items"][0]["id"]
    assert cliente.post(f"/notifications/{nid}/read", headers=admin_a).json()["lida_em"]
    assert _sino(cliente, admin_a)["nao_lidas"] == sino["nao_lidas"] - 1
    cliente.post("/notifications/read-all", headers=admin_a)
    assert _sino(cliente, admin_a)["nao_lidas"] == 0
    # não se marca a notificação de outro utilizador
    outra = _sino(cliente, geologo_a)["items"][0]["id"]
    assert cliente.post(f"/notifications/{outra}/read", headers=admin_a).status_code == 404
