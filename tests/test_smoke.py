import pytest


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_properties_public(client):
    resp = await client.get("/api/v1/properties")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_admin_overview_requires_auth(client):
    resp = await client.get("/api/v1/admin/overview")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_rejects_bad_credentials(client):
    resp = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"}
    )
    assert resp.status_code == 401
