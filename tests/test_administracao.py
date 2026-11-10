"""Empresas, utilizadores, perfis, áreas de projecto e litologias."""
from __future__ import annotations


def test_superadmin_cria_empresa_e_utilizador(cliente, superadmin, autenticar):
    resposta = cliente.post(
        "/companies", json={"nome": "Empresa C", "slug": "empresa-c"}, headers=superadmin,
    )
    assert resposta.status_code == 201, resposta.text
    empresa = resposta.json()

    cabecalhos = {**superadmin, "X-Company-ID": empresa["id"]}
    resposta = cliente.get("/roles", headers=cabecalhos)
    assert resposta.status_code == 200, resposta.text
    papeis = resposta.json()
    assert len(papeis) >= 10
    papel_admin = next(papel for papel in papeis if papel["codigo"] == "company_admin")

    resposta = cliente.post(
        "/users",
        json={"nome": "Admin C", "email": "admin.c@teste.ao", "senha": "admin12345",
              "role_id": papel_admin["id"]},
        headers=cabecalhos,
    )
    assert resposta.status_code == 201, resposta.text
    membro = resposta.json()
    assert membro["email"] == "admin.c@teste.ao"

    cabecalhos_c = autenticar("admin.c@teste.ao", "admin12345", empresa["id"])
    resposta = cliente.get("/users", headers=cabecalhos_c)
    assert resposta.status_code == 200
    assert resposta.json()[0]["role_codigo"] == "company_admin"

    resposta = cliente.patch(
        f"/companies/{empresa['id']}", json={"cidade": "Huambo"}, headers=cabecalhos_c,
    )
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["cidade"] == "Huambo"


def test_areas_e_litologias(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()

    resposta = cliente.post(
        f"/projects/{projeto['id']}/areas",
        json={"nome": "Área Norte", "area_km2": 5.0,
              "geometria": {"type": "Polygon",
                            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}},
        headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    area = resposta.json()

    resposta = cliente.get(f"/projects/{projeto['id']}/areas", headers=admin_a)
    assert resposta.status_code == 200
    assert len(resposta.json()) == 1

    resposta = cliente.patch(
        f"/projects/{projeto['id']}/areas/{area['id']}",
        json={"nome": "Área Norte Revista"}, headers=admin_a,
    )
    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Área Norte Revista"

    resposta = cliente.delete(
        f"/projects/{projeto['id']}/areas/{area['id']}", headers=admin_a,
    )
    assert resposta.status_code == 204

    resposta = cliente.post(
        "/lithologies", json={"codigo": "GRN", "nome": "Granito"}, headers=admin_a,
    )
    assert resposta.status_code == 201, resposta.text
    litologia = resposta.json()

    resposta = cliente.post(
        "/lithologies", json={"codigo": "GRN", "nome": "Duplicado"}, headers=admin_a,
    )
    assert resposta.status_code == 409

    resposta = cliente.patch(
        f"/lithologies/{litologia['id']}", json={"cor": "#aabbcc"}, headers=admin_a,
    )
    assert resposta.status_code == 200
    assert resposta.json()["cor"] == "#aabbcc"

    resposta = cliente.delete(f"/lithologies/{litologia['id']}", headers=admin_a)
    assert resposta.status_code == 204


def test_soft_delete_de_projecto(cliente, criar_projecto, admin_a):
    projeto = criar_projecto()
    resposta = cliente.delete(f"/projects/{projeto['id']}", headers=admin_a)
    assert resposta.status_code == 204

    resposta = cliente.get(f"/projects/{projeto['id']}", headers=admin_a)
    assert resposta.status_code == 404

    resposta = cliente.get("/projects", headers=admin_a)
    assert resposta.json()["total"] == 0

    resposta = cliente.get("/projects?incluir_eliminados=true", headers=admin_a)
    assert resposta.json()["total"] == 1
