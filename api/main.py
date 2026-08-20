"""
api/main.py — FastAPI Backend para RRFF Soft
============================================
Expone los datos de PostgreSQL al frontend React.
"""
import os
import sys
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Añadir la raíz del proyecto al path para importar módulos src/
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from api.routes import auth, sop, upload, maquila, maquila_ordenes, export

app = FastAPI(title="RRFF Soft API", version="2.1.0")

# CORS — permitir origenes locales y de produccion en Render
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]
env_front = os.getenv("FRONTEND_URL")
if env_front:
    allowed_origins.append(env_front.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router,   prefix="/api/auth",   tags=["Auth"])
app.include_router(sop.router,    prefix="/api/sop",    tags=["S&OP"])
app.include_router(upload.router, prefix="/api/upload", tags=["Upload"])
app.include_router(maquila.router, prefix="/api/maquila", tags=["Maquila"])
app.include_router(maquila_ordenes.router, prefix="/api/maquila/ordenes", tags=["Maquila Ordenes"])
app.include_router(export.router, prefix="/api/export", tags=["Export"])


@app.on_event("startup")
def on_startup():
    """Ejecuta migraciones DDL al arrancar la API."""
    from api.db import run_migrations
    run_migrations()


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.1.0"}
