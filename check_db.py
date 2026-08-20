from api.db import engine
from sqlalchemy import text

with engine.connect() as conn:
    r = conn.execute(text(
        "SELECT COUNT(*) as total, "
        "COUNT(CASE WHEN stock_act > 0 THEN 1 END) as con_stock, "
        "COALESCE(SUM(stock_act),0) as total_stock FROM dim_productos"
    )).fetchone()
    print(f"dim_productos => Total: {r[0]}, Con stock>0: {r[1]}, Stock sum: {r[2]}")

    r2 = conn.execute(text("SELECT COUNT(*) FROM planificacion_sop")).fetchone()
    print(f"planificacion_sop => Filas: {r2[0]}")

    r3 = conn.execute(text("SELECT COUNT(*) FROM control_embarques WHERE estado='EN_TRANSITO'")).fetchone()
    print(f"control_embarques EN_TRANSITO => {r3[0]}")

    # Ver sample de stock
    rows = conn.execute(text(
        "SELECT sku, codigo_femaco, stock_act FROM dim_productos WHERE stock_act > 0 LIMIT 5"
    )).fetchall()
    print("\nProductos con stock > 0:")
    for row in rows:
        print(f"  SKU={row[0]}, CF={row[1]}, stock={row[2]}")
    if not rows:
        print("  (ninguno)")
