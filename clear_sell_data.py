"""
clear_sell_data.py
------------------
Borra TODOS los datos de las tablas de Sell In y Sell Out (fact_ventas),
así como los datos de planificación derivados, para empezar desde cero
con datos reales cargados desde la matriz, maestra e inventario.
"""
import os
from sqlalchemy import text
from api.db import engine


def clear_sell_data():
    with engine.begin() as conn:
        print("=" * 55)
        print("  Limpiando datos ficticios de Sell In / Sell Out")
        print("=" * 55)

        # 1. Planificación SOP depende de fact_ventas → borrar primero
        result = conn.execute(text("SELECT COUNT(*) FROM planificacion_sop"))
        n_sop = result.scalar()
        conn.execute(text("TRUNCATE TABLE planificacion_sop RESTART IDENTITY CASCADE"))
        print(f"  [OK] planificacion_sop  - {n_sop} filas eliminadas")

        # 2. Sell In / Sell Out  (fact_ventas)
        result = conn.execute(text("SELECT COUNT(*) FROM fact_ventas"))
        n_ventas = result.scalar()
        conn.execute(text("TRUNCATE TABLE fact_ventas RESTART IDENTITY CASCADE"))
        print(f"  [OK] fact_ventas        - {n_ventas} filas eliminadas")

        print("=" * 55)
        print("  Listo! La BD queda limpia para datos reales.")
        print("  Proximos pasos:")
        print("   1. Subir Maestra       -> /upload/maestro")
        print("   2. Subir Inventario    -> /upload/inventario")
        print("   3. Sincronizar Matrix  -> boton Admin -> Sincronizar Matrix")
        print("=" * 55)


if __name__ == "__main__":
    clear_sell_data()
