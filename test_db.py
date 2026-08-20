import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    try:
        conn = psycopg2.connect(
            host=os.environ.get("DB_HOST", "localhost"),
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ.get("DB_NAME", "RRFF_AS_db"),
            user=os.environ.get("DB_USER", "postgres"),
            password=os.environ.get("DB_PASS", "")
        )
        print("Base de datos Up and Running!")
        conn.close()
    except Exception as e:
        print(f"Error al conectar a la base de datos: {e}")

if __name__ == "__main__":
    test_connection()
