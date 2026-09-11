import os
from sqlalchemy import create_engine, text

def get_engine():
    # Fallback local logic from api/db.py
    host = os.getenv("DB_HOST", "localhost").strip().strip('"')
    port = os.getenv("DB_PORT", "5432").strip().strip('"')
    name = os.getenv("DB_NAME", "RRFF_AS_db").strip().strip('"')
    user = os.getenv("DB_USER", "postgres").strip().strip('"')
    pwd  = os.getenv("DB_PASS", "postgres").strip().strip('"')
    return create_engine(
        f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}"
    )

def main():
    engine = get_engine()
    with engine.connect() as conn:
        # Total DB Size
        total_size_query = text("""
            SELECT 
                pg_size_pretty(pg_database_size(current_database())) AS formatted_size,
                pg_database_size(current_database()) / 1024.0 / 1024.0 AS size_mb,
                pg_database_size(current_database()) / 1024.0 / 1024.0 / 1024.0 AS size_gb
        """)
        total_size_res = conn.execute(total_size_query).fetchone()
        
        print("=== DATABASE TOTAL SIZE ===")
        print(f"Total Size: {total_size_res.formatted_size}")
        print(f"Size in MB: {total_size_res.size_mb:.2f} MB")
        print(f"Size in GB: {total_size_res.size_gb:.2f} GB")
        print("\n=== TOP 15 TABLES (DATA + INDEXES) ===")
        
        # Top 15 Tables Size
        top_tables_query = text("""
            SELECT
                relname AS table_name,
                pg_size_pretty(pg_total_relation_size(C.oid)) AS total_size,
                pg_total_relation_size(C.oid) / 1024.0 / 1024.0 AS raw_mb
            FROM pg_class C
            LEFT JOIN pg_namespace N ON (N.oid = C.relnamespace)
            WHERE nspname NOT IN ('pg_catalog', 'information_schema')
              AND C.relkind <> 'i'
              AND nspname !~ '^pg_toast'
            ORDER BY pg_total_relation_size(C.oid) DESC
            LIMIT 15;
        """)
        top_tables_res = conn.execute(top_tables_query).fetchall()
        
        print(f"{'Table Name':<30} | {'Total Size':<15} | {'Size (MB)':<10}")
        print("-" * 60)
        for row in top_tables_res:
            print(f"{row.table_name:<30} | {row.total_size:<15} | {row.raw_mb:.2f}")

if __name__ == '__main__':
    main()
