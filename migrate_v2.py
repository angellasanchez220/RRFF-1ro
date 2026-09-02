"""Migración DB v2 — separada por transacciones independientes."""
import hashlib
import json
import os

from sqlalchemy import text

from api.db import engine

def run(sql, params=None):
    try:
        with engine.begin() as conn:
            conn.execute(text(sql), params or {})
        print("OK:", sql[:70].replace('\n',' '))
    except Exception as e:
        print("SKIP:", str(e)[:120])

# fact_transito columns
run("ALTER TABLE fact_transito ADD COLUMN IF NOT EXISTS estado TEXT DEFAULT 'en_transito'")
run("ALTER TABLE fact_transito ADD COLUMN IF NOT EXISTS fecha_eta_original TEXT")
run("ALTER TABLE fact_transito ADD COLUMN IF NOT EXISTS fecha_eta_actualizada TEXT")
run("ALTER TABLE fact_transito ADD COLUMN IF NOT EXISTS fecha_llegada TEXT")
run("ALTER TABLE fact_transito ADD COLUMN IF NOT EXISTS observacion_oc TEXT")
run("UPDATE fact_transito SET estado = 'en_transito' WHERE estado IS NULL")
run("""UPDATE fact_transito
       SET fecha_eta_original = CAST(fecha_eta AS TEXT)
       WHERE fecha_eta_original IS NULL AND fecha_eta IS NOT NULL""")

# Añadir columna id solo si no existe
run("""DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='fact_transito' AND column_name='id') THEN
        ALTER TABLE fact_transito ADD COLUMN id SERIAL;
    END IF;
END $$""")

# observaciones_sop
run("""CREATE TABLE IF NOT EXISTS observaciones_sop (
    id SERIAL PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    texto TEXT,
    creado_por TEXT,
    creado_en TIMESTAMP DEFAULT NOW(),
    modificado_por TEXT,
    modificado_en TIMESTAMP
)""")

# usuarios
run("""CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    rol TEXT DEFAULT 'viewer',
    activo BOOLEAN DEFAULT TRUE,
    permisos JSONB DEFAULT '{}'::jsonb,
    creado_en TIMESTAMP DEFAULT NOW()
)""")

# Insertar admin solo con una credencial entregada por el entorno.
admin_perms = json.dumps({
    "can_upload_maestro": True, "can_upload_inventario": True,
    "can_upload_transito": True, "can_manage_transito": True,
    "can_edit_obs": True, "can_manage_users": True
})
admin_user = os.getenv("ADMIN_USER", "admin")
admin_pass = os.getenv("ADMIN_PASS")
if not admin_pass:
    print("SKIP admin: falta ADMIN_PASS en el entorno")
else:
    try:
        admin_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO usuarios (username, password_hash, rol, permisos) "
                "VALUES (:u, :h, 'admin', CAST(:p AS jsonb)) "
                "ON CONFLICT (username) DO NOTHING"
            ), {"u": admin_user, "h": admin_hash, "p": admin_perms})
        print("OK: admin user")
    except Exception as e:
        print("SKIP admin:", e)

engine.dispose()
print("\nMIGRATION DONE")
