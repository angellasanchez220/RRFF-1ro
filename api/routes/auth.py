"""
api/routes/auth.py — Autenticación JWT con usuarios en PostgreSQL
Roles: admin | viewer | custom
Permisos granulares en JSONB por usuario.
"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, Header, HTTPException, status
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import text

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

router = APIRouter()

SECRET_KEY  = os.getenv("JWT_SECRET", "rrff-soft-secret-2026-change-me")
ALGORITHM   = "HS256"
TOKEN_HOURS = 8

# Permisos por defecto para cada rol
DEFAULT_PERMISOS = {
    "admin": {
        "can_upload_maestro":     True,
        "can_upload_inventario":  True,
        "can_upload_transito":    True,
        "can_edit_obs":           True,
        "can_manage_oc":          True,
        "can_manage_users":       True,
    },
    "viewer": {
        "can_upload_maestro":     False,
        "can_upload_inventario":  False,
        "can_upload_transito":    False,
        "can_edit_obs":           False,
        "can_manage_oc":          False,
        "can_manage_users":       False,
    },
}


# ── Modelos ───────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str
    permisos: dict

class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    permisos: dict = {}

class UpdateUserRequest(BaseModel):
    password: str | None = None
    role: str | None = None
    permisos: dict | None = None
    activo: bool | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(pwd: str) -> str:
    return hashlib.sha256(pwd.encode()).hexdigest()


def create_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")


def _get_auth_header(authorization: str = Header(None)) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="No autenticado")
    return authorization.replace("Bearer ", "")

def require_authenticated(authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    return decode_token(token)


def require_permission(perm: str):
    """Factory: retorna un Depends que valida que el token tenga el permiso."""
    def checker(authorization: str = Header(None)):
        token = _get_auth_header(authorization)
        payload = decode_token(token)
        permisos = payload.get("permisos", {})
        role = payload.get("role", "")
        if role == "admin" or permisos.get(perm):
            return payload
        raise HTTPException(status_code=403, detail=f"Permiso requerido: {perm}")
    return checker


def require_admin(authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Se requiere rol admin")
    return payload


def _get_user_from_db(username: str):
    from api.db import engine
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT username, password_hash, role, permisos, activo FROM usuarios WHERE username=:u"),
            {"u": username}
        ).fetchone()
    return row


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    row = _get_user_from_db(body.username)
    if not row or row.password_hash != _hash(body.password) or not row.activo:
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    permisos = row.permisos if isinstance(row.permisos, dict) else (
        json.loads(row.permisos) if row.permisos else {}
    )
    # Rol admin siempre tiene todos los permisos
    if row.role == "admin":
        permisos = DEFAULT_PERMISOS["admin"]

    token = create_token({"sub": row.username, "role": row.role, "permisos": permisos})
    return {
        "access_token": token,
        "token_type":   "bearer",
        "role":         row.role,
        "username":     row.username,
        "permisos":     permisos,
    }


@router.get("/me")
def get_me(authorization: str = Header(None)):
    token = _get_auth_header(authorization)
    payload = decode_token(token)
    return {
        "username": payload.get("sub"),
        "role":     payload.get("role"),
        "permisos": payload.get("permisos", {}),
    }


# ── CRUD de Usuarios (solo admin) ─────────────────────────────────────────────

@router.get("/usuarios")
def list_usuarios(payload: dict = Depends(require_admin)):
    from api.db import engine
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT username, role, permisos, activo, creado_en FROM usuarios ORDER BY username"
        )).fetchall()
    return [
        {
            "username":  r.username,
            "role":      r.role,
            "permisos":  r.permisos if isinstance(r.permisos, dict) else (json.loads(r.permisos) if r.permisos else {}),
            "activo":    r.activo,
            "creado_en": str(r.creado_en)[:10] if r.creado_en else None,
        }
        for r in rows
    ]


@router.post("/usuarios")
def create_usuario(body: CreateUserRequest, payload: dict = Depends(require_admin)):
    from api.db import engine
    # Si no se especifican permisos, usar defaults del rol
    permisos = body.permisos if body.permisos else DEFAULT_PERMISOS.get(body.role, {})
    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM usuarios WHERE username=:u"), {"u": body.username}
        ).fetchone()
        if exists:
            raise HTTPException(400, "El usuario ya existe")
        conn.execute(text("""
            INSERT INTO usuarios (username, password_hash, role, permisos, activo)
            VALUES (:u, :h, :r, :p, TRUE)
        """), {
            "u": body.username,
            "h": _hash(body.password),
            "r": body.role,
            "p": json.dumps(permisos),
        })
    return {"ok": True, "username": body.username}


@router.put("/usuarios/{username}")
def update_usuario(username: str, body: UpdateUserRequest, payload: dict = Depends(require_admin)):
    from api.db import engine
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT 1 FROM usuarios WHERE username=:u"), {"u": username}
        ).fetchone()
        if not row:
            raise HTTPException(404, "Usuario no encontrado")

        updates = []
        params  = {"u": username}
        if body.password is not None:
            updates.append("password_hash=:h")
            params["h"] = _hash(body.password)
        if body.role is not None:
            updates.append("role=:r")
            params["r"] = body.role
        if body.permisos is not None:
            updates.append("permisos=:p")
            params["p"] = json.dumps(body.permisos)
        if body.activo is not None:
            updates.append("activo=:a")
            params["a"] = body.activo

        if updates:
            conn.execute(
                text(f"UPDATE usuarios SET {', '.join(updates)} WHERE username=:u"),
                params
            )
    return {"ok": True}


@router.delete("/usuarios/{username}")
def delete_usuario(username: str, payload: dict = Depends(require_admin)):
    from api.db import engine
    # No se puede eliminar a sí mismo
    if username == payload.get("sub"):
        raise HTTPException(400, "No puedes eliminar tu propio usuario")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM usuarios WHERE username=:u"), {"u": username})
    return {"ok": True}
