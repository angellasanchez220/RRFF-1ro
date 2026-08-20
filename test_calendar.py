"""Verifica el calendario y grafico con el mapeo real de columnas."""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from api.db import engine
from api.routes.sop import _build_month_calendar, _build_chart_12m
from sqlalchemy import text
import pandas as pd

with engine.connect() as conn:
    df = pd.read_sql(text("SELECT * FROM planificacion_sop WHERE sku='7064098'"), conn)

row = df.iloc[0].to_dict()
cols = list(df.columns)

print("=== CALENDARIO (Ene->Dic) ===")
cal = _build_month_calendar(cols, row)
for m in cal:
    print(f"  {m['label']:22s}  SO={m['sell_out']:5d}  SI={m['sell_in']:5d}")

print("\n=== GRAFICO (cronologico May2025->Abr2026) ===")
chart = _build_chart_12m(cols, row)
for m in chart:
    print(f"  {m['name']:14s}  SO={m['Sell Out']:5d}  SI={m['Sell In']:5d}")
