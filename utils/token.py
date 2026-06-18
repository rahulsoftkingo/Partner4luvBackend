# utils/token.py
from datetime import datetime, timedelta, timezone
from jose import jwt

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=30)  # access token expiry
    payload["type"] = "access"

    return jwt.encode(
        payload,
        "secret123",
        algorithm="HS256"
    )

def create_refresh_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(days=7)  # refresh token expiry
    payload["type"] = "refresh"

    return jwt.encode(
        payload,
        "secret123",
        algorithm="HS256"
    )