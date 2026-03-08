import pytest


class TestRegisterEndpoint:
    async def test_register_success(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "password123",
                "full_name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "newuser@example.com"
        assert data["full_name"] == "New User"
        assert data["is_active"] is True
        assert "hashed_password" not in data
        assert "id" in data

    async def test_register_duplicate_email(self, client):
        await client.post(
            "/api/v1/auth/register",
            json={"email": "duplicate@example.com", "password": "password123"},
        )
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "duplicate@example.com", "password": "password456"},
        )
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    async def test_register_invalid_email(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "notanemail", "password": "password123"},
        )
        assert response.status_code == 422

    async def test_register_missing_password(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com"},
        )
        assert response.status_code == 422

    async def test_register_short_password(self, client):
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@example.com", "password": "short"},
        )
        assert response.status_code == 422


class TestLoginEndpoint:
    async def test_login_success(self, client, test_user):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@example.com", "password": "testpass123"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 0

    async def test_login_wrong_password(self, client, test_user):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password"

    async def test_login_nonexistent_email(self, client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "password123"},
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Incorrect email or password"

    async def test_login_wrong_password_same_error_as_wrong_email(self, client, test_user):
        wrong_pass = await client.post(
            "/api/v1/auth/login",
            json={"email": "testuser@example.com", "password": "wrongpassword"},
        )
        wrong_email = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "testpass123"},
        )
        assert wrong_pass.json()["detail"] == wrong_email.json()["detail"]


class TestMeEndpoint:
    async def test_me_success(self, client, auth_headers, test_user):
        response = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "testuser@example.com"
        assert data["full_name"] == "Test User"
        assert "hashed_password" not in data

    async def test_me_no_token(self, client):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 403

    async def test_me_invalid_token(self, client):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalidtoken"},
        )
        assert response.status_code == 401

    async def test_me_malformed_header(self, client):
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "notbearer token"},
        )
        assert response.status_code == 403