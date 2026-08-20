import os
from sqlalchemy import text
from api.db import engine

def list_tables():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
        for row in result:
            print(row[0])

if __name__ == "__main__":
    list_tables()
