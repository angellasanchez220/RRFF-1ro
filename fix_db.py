import psycopg2
conn = psycopg2.connect('postgresql://postgres:postgres@localhost:5432/RRFF_AS_db')
cur = conn.cursor()
cur.execute("UPDATE dim_productos SET estado = condicion WHERE condicion IS NOT NULL AND condicion != ''")
conn.commit()
print('Filas actualizadas:', cur.rowcount)
