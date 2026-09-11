import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/RRFF_AS_db')
cur = conn.cursor()
cur.execute("SELECT sku, estado, excepciones FROM planificacion_sop WHERE sku='5523613'")
print(cur.fetchone())
