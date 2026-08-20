"""Test completo: sem1 desde fact_ventas + calendario."""
from api.db import engine
from api.routes.sop import _get_semanas_fact_ventas, _build_month_calendar
from sqlalchemy import text
import pandas as pd

with engine.connect() as conn:
    sem_map = _get_semanas_fact_ventas(conn)
    # Ver CINTA ANTIDES
    sku = '7064098'
    print(f"SEMANAS desde fact_ventas para SKU {sku}:")
    for k, v in sem_map.get(sku, {}).items():
        print(f"  {k} = {v}")

    # Mostrar 3 SKUs que tienen sem1 > 0
    count_con_sem1 = sum(1 for s in sem_map.values() if s.get('sem1_uds', 0) > 0)
    print(f"\nSKUs con sem1 > 0: {count_con_sem1} de {len(sem_map)}")
    for s, d in list(sem_map.items())[:5]:
        print(f"  SKU {s}: sem1={d['sem1_uds']}, sem2={d['sem2_uds']}, sem3={d['sem3_uds']}, sem4={d['sem4_uds']}, total={d['total_4_sem_verificado']}")
