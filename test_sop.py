"""Test rápido del endpoint SOP para verificar el calendario."""
from api.db import engine
from api.routes.sop import _build_month_calendar, _safe
from sqlalchemy import text
import pandas as pd
from datetime import date

with engine.connect() as conn:
    df = pd.read_sql(text(
        "SELECT * FROM planificacion_sop WHERE nombre_producto ILIKE '%antides%' LIMIT 1"
    ), conn)

if df.empty:
    print("No se encontró producto ANTIDES")
    # Mostrar qué hay con buscar antideslizante
    with engine.connect() as conn:
        df2 = pd.read_sql(text("SELECT sku, nombre_producto, categoria, subcategoria FROM planificacion_sop LIMIT 5"), conn)
    print("Muestra de productos:")
    print(df2.to_string())
else:
    row = df.iloc[0]
    print(f"Producto: {row['nombre_producto']}")
    print(f"SKU: {row['sku']} | CÓD: {row['codigo_femaco']}")
    print(f"ump={row.get('ump')} | stock_act={row.get('stock_act')}")
    print(f"sem1={row.get('sem1_uds')} | sem2={row.get('sem2_uds')} | sem3={row.get('sem3_uds')} | sem4={row.get('sem4_uds')}")
    print(f"total_4_sem_verificado={row.get('total_4_sem_verificado')}")
    print(f"sellout_mes_anterior_estimado={row.get('sellout_mes_anterior_estimado')}")
    print()

    cols = list(df.columns)
    row_dict = row.to_dict()
    cal = _build_month_calendar(cols, row_dict)
    print("CALENDARIO:")
    for m in cal:
        print(f"  {m['label']:20s} SO={m['sell_out']:6d}  SI={m['sell_in']:6d}  {'real' if m['es_real'] else ''}")
