"""
Diagnostico: origen de datos Sell In / Sell Out
"""
import os
import sys
os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
import pandas as pd
from datetime import datetime

RAW  = Path(r"c:\Users\GH\Desktop\femaco\RRFF soft\data\raw")
PROC = Path(r"c:\Users\GH\Desktop\femaco\RRFF soft\data\processed")

print("=" * 60)
print("ARCHIVOS RAW (data/raw)")
print("=" * 60)
for f in sorted(RAW.iterdir()):
    mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    size_mb = f.stat().st_size / 1_000_000
    print(f"  {f.name:<35} {size_mb:>8.2f} MB   mod: {mtime}")

print()
print("=" * 60)
print("PRIMERAS FILAS: sellin_historico.csv")
print("=" * 60)
try:
    df_si = pd.read_csv(RAW / "sellin_historico.csv", nrows=3, sep=None, engine="python", encoding="utf-8-sig")
    print(f"  Columnas ({len(df_si.columns)}): {list(df_si.columns[:8])}")
    print(df_si.iloc[:, :6].to_string(index=False))
except Exception as e:
    print(f"  Error: {e}")

print()
print("=" * 60)
print("PRIMERAS FILAS: sellout_historico.csv")
print("=" * 60)
try:
    df_so = pd.read_csv(RAW / "sellout_historico.csv", nrows=3, sep=None, engine="python", encoding="utf-8-sig")
    print(f"  Columnas ({len(df_so.columns)}): {list(df_so.columns[:8])}")
    print(df_so.iloc[:, :6].to_string(index=False))
except Exception as e:
    print(f"  Error: {e}")

print()
print("=" * 60)
print("COLUMNAS SELL en planificacion_sop (DB)")
print("=" * 60)
try:
    from api.db import engine
    from sqlalchemy import text
    with engine.connect() as conn:
        df_sop = pd.read_sql(text("SELECT * FROM planificacion_sop LIMIT 3"), conn)
    sell_cols = [c for c in df_sop.columns if "sellout" in c or "sellin" in c]
    print(f"  Total columnas sell: {len(sell_cols)}")
    print(f"  Nombres: {sell_cols}")
    print()
    if sell_cols:
        for col in sell_cols[:6]:
            vals = pd.to_numeric(df_sop[col], errors="coerce").fillna(0)
            non_zero = (vals > 0).sum()
            print(f"    {col}: valores = {list(vals)}, no-cero = {non_zero}/{len(df_sop)}")
except Exception as e:
    print(f"  Error DB: {e}")
