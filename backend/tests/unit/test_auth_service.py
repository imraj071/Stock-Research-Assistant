import pytest
from datetime import timedelta
from app.services.auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    create_user,
    authenticate_user,
    get_user_by_email,
)


class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        result = hash_password("testpassword123")
        assert isinstance(result, str)

    def test_hash_password_not_plaintext(self):
        result = hash_password("testpassword123")
        assert result != "testpassword123"

    def test_hash_password_starts_with_bcrypt_prefix(self):
        result = hash_password("testpassword123")
        assert result.startswith("$2b$")

    def test_verify_password_correct(self):
        hashed = hash_password("testpassword123")
        assert verify_password("testpassword123", hashed) is True

    def test_verify_password_wrong(self):
        hashed = hash_password("testpassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_hash_password_different_each_time(self):
        hash1 = hash_password("testpassword123")
        hash2 = hash_password("testpassword123")
        assert hash1 != hash2


class TestJWT:
    def test_create_access_token_returns_string(self):
        token = create_access_token(subject=1)
        assert isinstance(token, str)

    def test_create_access_token_decodable(self):
        token = create_access_token(subject=1)
        payload = decode_access_token(token)
        assert payload is not None

    def test_create_access_token_correct_subject(self):
        token = create_access_token(subject=42)
        payload = decode_access_token(token)
        assert payload["sub"] == "42"

    def test_create_access_token_has_expiry(self):
        token = create_access_token(subject=1)
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_create_access_token_custom_expiry(self):
        token = create_access_token(
            subject=1,
            expires_delta=timedelta(minutes=30),
        )
        payload = decode_access_token(token)
        assert payload is not None

    def test_decode_invalid_token_returns_none(self):
        result = decode_access_token("not.a.valid.token")
        assert result is None

    def test_decode_tampered_token_returns_none(self):
        token = create_access_token(subject=1)
        tampered = token[:-5] + "XXXXX"
        result = decode_access_token(tampered)
        assert result is None


class TestUserCreation:
    async def test_create_user_success(self, db):
        user = await create_user(
            db=db,
            email="newuser@example.com",
            password="password123",
            full_name="New User",
        )
        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.full_name == "New User"
        assert user.is_active is True

    async def test_create_user_email_lowercase(self, db):
        user = await create_user(
            db=db,
            email="UPPERCASE@EXAMPLE.COM",
            password="password123",
        )
        assert user.email == "uppercase@example.com"

    async def test_create_user_password_hashed(self, db):
        user = await create_user(
            db=db,
            email="hashtest@example.com",
            password="password123",
        )
        assert user.hashed_password != "password123"
        assert user.hashed_password.startswith("$2b$")

    async def test_create_user_duplicate_email_raises(self, db):
        await create_user(
            db=db,
            email="duplicate@example.com",
            password="password123",
        )
        with pytest.raises(ValueError, match="already exists"):
            await create_user(
                db=db,
                email="duplicate@example.com",
                password="password456",
            )

    async def test_get_user_by_email_found(self, db):
        await create_user(
            db=db,
            email="findme@example.com",
            password="password123",
        )
        user = await get_user_by_email(db, "findme@example.com")
        assert user is not None
        assert user.email == "findme@example.com"

    async def test_get_user_by_email_not_found(self, db):
        user = await get_user_by_email(db, "nonexistent@example.com")
        assert user is None


class TestAuthentication:
    async def test_authenticate_user_success(self, db):
        await create_user(
            db=db,
            email="authtest@example.com",
            password="password123",
        )
        user = await authenticate_user(
            db=db,
            email="authtest@example.com",
            password="password123",
        )
        assert user is not None
        assert user.email == "authtest@example.com"

    async def test_authenticate_user_wrong_password(self, db):
        await create_user(
            db=db,
            email="wrongpass@example.com",
            password="password123",
        )
        user = await authenticate_user(
            db=db,
            email="wrongpass@example.com",
            password="wrongpassword",
        )
        assert user is None

    async def test_authenticate_user_nonexistent_email(self, db):
        user = await authenticate_user(
            db=db,
            email="nobody@example.com",
            password="password123",
        )
        assert user is None

    async def test_authenticate_inactive_user_returns_none(self, db):
        user = await create_user(
            db=db,
            email="inactive@example.com",
            password="password123",
        )
        user.is_active = False
        await db.commit()

        result = await authenticate_user(
            db=db,
            email="inactive@example.com",
            password="password123",
        )
        assert result is None