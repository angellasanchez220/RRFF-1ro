"""Resetea la contraseña del administrador usando variables de entorno."""
import hashlib
import os
from api.db import engine
from sqlalchemy import text

admin_user = os.getenv("ADMIN_USER", "admin")
admin_pass = os.getenv("ADMIN_PASS")
if not admin_pass:
    raise RuntimeError("Falta ADMIN_PASS en el entorno; no se modificó el administrador")
pwd_hash = hashlib.sha256(admin_pass.encode()).hexdigest()

with engine.begin() as conn:
    # Verificar si existe
    row = conn.execute(
        text("SELECT username, role FROM usuarios WHERE username = :u"),
        {"u": admin_user}
    ).fetchone()

    if row:
        conn.execute(text("""
            UPDATE usuarios
            SET password_hash = :h,
                role = 'admin',
                permisos = :p,
                activo = TRUE
            WHERE username = :u
        """), {
            "u": admin_user,
            "h": pwd_hash,
            "p": '{"can_upload_maestro":true,"can_upload_inventario":true,'
                 '"can_upload_transito":true,"can_edit_obs":true,'
                 '"can_manage_oc":true,"can_manage_users":true}'
        })
        print(f"[OK] Password de '{admin_user}' actualizado desde ADMIN_PASS")
    else:
        conn.execute(text("""
            INSERT INTO usuarios (username, password_hash, role, permisos, activo)
            VALUES (:u, :h, 'admin', :p, TRUE)
        """), {
            "u": admin_user,
            "h": pwd_hash,
            "p": '{"can_upload_maestro":true,"can_upload_inventario":true,'
                 '"can_upload_transito":true,"can_edit_obs":true,'
                 '"can_manage_oc":true,"can_manage_users":true}'
        })
        print(f"[OK] Usuario admin '{admin_user}' creado desde ADMIN_PASS")

    # Listar usuarios
    rows = conn.execute(text("SELECT username, role, activo FROM usuarios")).fetchall()
    print("\nUsuarios en la BD:")
    for r in rows:
        print(f"  {r[0]:20s} role={r[1]:10s} activo={r[2]}")
