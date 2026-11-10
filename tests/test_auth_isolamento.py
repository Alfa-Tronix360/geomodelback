"""Autenticação, sessão e isolamento entre empresas."""
from __future__ import annotations


def test_login_me_e_alteracao_de_senha(cliente, bd, autenticar):
    cabecalhos = autenticar("admin.a@teste.ao", "admin12345", bd["empresa_a"])

    resposta = cliente.get("/auth/me", headers=cabecalhos)
    assert resposta.status_code == 200, resposta.text
    perfil = resposta.json()
    assert perfil["empresa_actual"]["slug"] == "empresa-a"
    assert perfil["papel"] == "company_admin"
    assert "projects:view" in perfil["permissoes"]

    resposta = cliente.post(
        "/auth/alterar-senha",
        json={"senha_actual": "admin12345", "senha_nova": "novaSenha123"},
        headers=cabecalhos,
    )
    assert resposta.status_code == 204, resposta.text

    resposta = cliente.post("/auth/login", json={"email": "admin.a@teste.ao", "senha": "admin12345"})
    assert resposta.status_code == 401
    resposta = cliente.post("/auth/login", json={"email": "admin.a@teste.ao", "senha": "novaSenha123"})
    assert resposta.status_code == 200


def test_acesso_sem_token(cliente, bd):
    resposta = cliente.get("/projects")
    assert resposta.status_code == 401


def test_superadmin_ve_todas_as_empresas(cliente, superadmin):
    resposta = cliente.get("/companies", headers=superadmin)
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["total"] == 2

    resposta = cliente.get("/auth/me", headers=superadmin)
    assert resposta.status_code == 200
    assert resposta.json()["permissoes"] == ["*"]


def test_isolamento_entre_empresas(cliente, bd, criar_projecto, admin_b, admin_a):
    projeto = criar_projecto()

    resposta = cliente.get("/projects", headers=admin_b)
    assert resposta.status_code == 200
    assert resposta.json()["total"] == 0

    resposta = cliente.get(f"/projects/{projeto['id']}", headers=admin_b)
    assert resposta.status_code == 404

    resposta = cliente.post(
        "/drill-holes",
        json={"project_id": projeto["id"], "codigo": "F-B"},
        headers=admin_b,
    )
    assert resposta.status_code == 422

    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "codigo": "AM-B"},
        headers=admin_b,
    )
    assert resposta.status_code == 422


def test_permissoes_do_geologo(cliente, criar_projecto, geologo_a):
    projeto = criar_projecto()

    resposta = cliente.post(
        "/lithologies", json={"codigo": "XST", "nome": "Xisto"}, headers=geologo_a,
    )
    assert resposta.status_code == 403

    resposta = cliente.post(
        "/drill-holes", json={"project_id": projeto["id"], "codigo": "F-GEO"}, headers=geologo_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.delete(f"/projects/{projeto['id']}", headers=geologo_a)
    assert resposta.status_code == 403


def test_tecnico_de_laboratorio_cria_resultados_mas_nao_projectos(cliente, criar_projecto,
                                                                   criar_furo, criar_laboratorio,
                                                                   admin_a, lab_a):
    projeto = criar_projecto()
    furo = criar_furo(projeto["id"])
    laboratorio = criar_laboratorio()
    resposta = cliente.post(
        "/samples",
        json={"project_id": projeto["id"], "drill_hole_id": furo["id"], "codigo": "AM-LAB",
              "de": 10, "ate": 12},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    amostra = resposta.json()

    resposta = cliente.post(
        "/assays",
        json={"sample_id": amostra["id"], "laboratory_id": laboratorio["id"],
              "parametro": "Cu", "valor": 1.1, "unidade": "%"},
        headers=lab_a,
    )
    assert resposta.status_code == 201, resposta.text

    resposta = cliente.post(
        "/projects", json={"codigo": "PRJ-LAB", "nome": "Projecto Lab"}, headers=lab_a,
    )
    assert resposta.status_code == 403
