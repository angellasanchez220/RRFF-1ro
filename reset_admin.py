"""
reset_admin.py — Resetea la contrasena del admin a rrff2026
"""
import hashlib
from api.db import engine
from sqlalchemy import text

admin_user = "admin"
admin_pass = "rrff2026"
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
        print(f"[OK] Password de '{admin_user}' reseteada a 'rrff2026'")
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
        print(f"[OK] Usuario admin creado con password 'rrff2026'")

    # Listar usuarios
    rows = conn.execute(text("SELECT username, role, activo FROM usuarios")).fetchall()
    print("\nUsuarios en la BD:")
    for r in rows:
        print(f"  {r[0]:20s} role={r[1]:10s} activo={r[2]}")
