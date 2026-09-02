"""
api/db.py — Engine SQLAlchemy compartido + migraciones automáticas
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def get_engine():
    # Render y despliegues en la nube: URL de base de datos directa
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)
        elif db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return create_engine(
            db_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 10},
        )
    
    # Fallback local
    host = os.getenv("DB_HOST", "localhost").strip().strip('"')
    port = os.getenv("DB_PORT", "5432").strip().strip('"')
    name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
    user = os.getenv("DB_USER", "postgres").strip().strip('"')
    pwd_env = os.getenv("DB_PASS")
    if not pwd_env:
        raise RuntimeError(
            "Falta configuración de base de datos: define DATABASE_URL o DB_PASS."
        )
    pwd = pwd_env.strip().strip('"')
    return create_engine(
        f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 10},
    )


engine = get_engine()


def run_migrations():
    """
    Ejecuta migraciones DDL idempotentes al arrancar la API.
    Todas usan IF NOT EXISTS / ADD COLUMN IF NOT EXISTS para ser seguras.
    """
    stmts = [
        # ── dim_productos: asegurar columna ump (U/E desde col T maestra) ─────
        "ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS ump FLOAT",
        "ALTER TABLE dim_productos ADD COLUMN IF NOT EXISTS condicion TEXT",

        # ── Observaciones por SKU ─────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS sku_observaciones (
            sku                TEXT PRIMARY KEY,
            observacion        TEXT,
            usuario            TEXT,
            fecha_modificacion TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── Usuarios con permisos granulares ─────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            username      TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role          TEXT DEFAULT 'viewer',
            permisos      JSONB DEFAULT '{}',
            activo        BOOLEAN DEFAULT TRUE,
            creado_en     TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── Control de embarques (OCs) con gestión aforo/ETA/llegada ─────────
        """
        CREATE TABLE IF NOT EXISTS control_embarques (
            id                       SERIAL PRIMARY KEY,
            codigo_envio             TEXT,
            nombre_pedido            TEXT,
            sku                      TEXT,
            codigo_femaco            TEXT,
            nombre_producto          TEXT,
            cantidad                 INTEGER DEFAULT 0,
            fecha_eta                DATE,
            fecha_disponibilidad_real DATE,
            origen_eta               TEXT,
            nombre_archivo           TEXT,
            estado                   TEXT DEFAULT 'EN_TRANSITO',
            en_aforo                 BOOLEAN DEFAULT FALSE,
            fecha_marcado_aforo      DATE,
            eta_ajustada             DATE,
            fecha_llegada_real       DATE,
            observacion              TEXT,
            creado_en                TIMESTAMP DEFAULT NOW(),
            actualizado_en           TIMESTAMP DEFAULT NOW()
        )
        """,
        # ── Asegurar nombre_pedido si la tabla ya existía sin esa columna ──────
        "ALTER TABLE control_embarques ADD COLUMN IF NOT EXISTS nombre_pedido TEXT",

        # ── Configuración Cobertura Objetivo ─────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS config_cobertura (
            tipo_regla TEXT NOT NULL,
            clave      TEXT NOT NULL,
            meses      FLOAT NOT NULL,
            PRIMARY KEY (tipo_regla, clave)
        )
        """,
    ] + [
        # ── Maquila: Recetas de Fabricación ──
        """
        CREATE TABLE IF NOT EXISTS recetas_maquila (
            id                  SERIAL PRIMARY KEY,
            sku_maquilable      TEXT NOT NULL,
            nombre_receta       TEXT,
            descripcion         TEXT,
            activa              BOOLEAN DEFAULT TRUE,
            fecha_creacion      TIMESTAMP DEFAULT NOW(),
            fecha_actualizacion TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── Maquila: Componentes de Receta ───────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS receta_maquila_componentes (
            id                  SERIAL PRIMARY KEY,
            receta_id           INTEGER NOT NULL REFERENCES recetas_maquila(id) ON DELETE CASCADE,
            sku_componente      TEXT NOT NULL,
            cantidad_por_unidad NUMERIC(12,4) NOT NULL,
            no_transformable    BOOLEAN NOT NULL DEFAULT FALSE,
            observacion         TEXT,
            fecha_creacion      TIMESTAMP DEFAULT NOW(),
            fecha_actualizacion TIMESTAMP DEFAULT NOW()
        )
        """,

        # ── Maquila: Índice único para receta activa ─────────────────────────
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_receta_activa ON recetas_maquila (sku_maquilable) WHERE activa = TRUE",

        # ── Maquila: Forzar tipo NUMERIC ─────────────────────────────────────
        "ALTER TABLE receta_maquila_componentes ADD COLUMN IF NOT EXISTS no_transformable BOOLEAN NOT NULL DEFAULT FALSE",
        "ALTER TABLE receta_maquila_componentes ALTER COLUMN cantidad_por_unidad TYPE NUMERIC(12,4)",

        # ── Órdenes de Maquila ───────────────────────────────────────────────
        """
        CREATE TABLE IF NOT EXISTS ordenes_maquila (
            id                     SERIAL PRIMARY KEY,
            numero_oc              TEXT NOT NULL,
            nombre_archivo         TEXT,
            estado_oc              TEXT,
            tipo_orden             TEXT,
            fecha_emision          DATE,
            fecha_inicio_recepcion DATE,
            fecha_fin_recepcion    DATE,
            fecha_carga            TIMESTAMP DEFAULT NOW(),
            usuario_carga          TEXT,
            estado_procesamiento   TEXT DEFAULT 'Pendiente',
            observaciones          TEXT,
            activa                 BOOLEAN DEFAULT TRUE,
            hash_archivo           TEXT NOT NULL,
            UNIQUE(numero_oc, hash_archivo)
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS orden_maquila_detalle (
            id                       SERIAL PRIMARY KEY,
            orden_id                 INTEGER NOT NULL REFERENCES ordenes_maquila(id) ON DELETE CASCADE,
            sku                      TEXT NOT NULL,
            nombre_producto          TEXT,
            cantidad_solicitada      INTEGER NOT NULL DEFAULT 0,
            cantidad_recibida        INTEGER NOT NULL DEFAULT 0,
            cantidad_pendiente       INTEGER NOT NULL DEFAULT 0,
            es_maquilable            BOOLEAN DEFAULT FALSE,
            receta_maquila_id        INTEGER,
            stock_producto_terminado INTEGER DEFAULT 0,
            cantidad_a_maquilar      INTEGER DEFAULT 0,
            estado_analisis          TEXT,
            observacion              TEXT
        )
        """,

        """
        CREATE TABLE IF NOT EXISTS orden_maquila_distribucion (
            id                 SERIAL PRIMARY KEY,
            orden_id           INTEGER NOT NULL REFERENCES ordenes_maquila(id) ON DELETE CASCADE,
            sku                TEXT NOT NULL,
            id_local           TEXT,
            local              TEXT,
            unidades_compradas INTEGER DEFAULT 0,
            unidades_recibidas INTEGER DEFAULT 0,
            cantidad_empaque   INTEGER DEFAULT 0
        )
        """,
    ]


    for stmt in stmts:
        try:
            with engine.begin() as conn:
                conn.execute(text(stmt))
        except Exception as e:
            # Ignorar errores menores de migración (p.ej. tabla o columna no existe aún)
            pass

    # Insertar admin por defecto si la tabla usuarios está vacía
    _seed_admin_user()


def _seed_admin_user():
    """Inserta el usuario admin por defecto si no existe ninguno."""
    import hashlib

    admin_user = os.getenv("ADMIN_USER", "admin")
    admin_pass = os.getenv("ADMIN_PASS")

    with engine.begin() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM usuarios WHERE username = :u"),
            {"u": admin_user}
        ).fetchone()
        if exists:
            return

        if not admin_pass:
            raise RuntimeError(
                "No existen usuarios y falta ADMIN_PASS. Define una contraseña segura "
                "para crear el administrador inicial."
            )

        # Hash simple SHA-256 (compatibilidad con el esquema de autenticación actual)
        pwd_hash = hashlib.sha256(admin_pass.encode()).hexdigest()
        conn.execute(text("""
            INSERT INTO usuarios (username, password_hash, role, permisos, activo)
            VALUES (:u, :h, 'admin', :p, TRUE)
            ON CONFLICT (username) DO NOTHING
        """), {
            "u": admin_user,
            "h": pwd_hash,
            "p": '{"can_upload_maestro":true,"can_upload_inventario":true,'
                 '"can_upload_transito":true,"can_edit_obs":true,'
                 '"can_manage_oc":true,"can_manage_users":true}'
        })
