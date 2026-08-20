import httpx

# Login to get token
r_login = httpx.post("http://127.0.0.1:8000/api/auth/login", data={"username": "admin", "password": "rrff2026"})
token = r_login.json()["access_token"]

with open("data/manual_uploads/ordenes_compra/OC-2026-0047_CINTAS.xlsx", "rb") as f:
    files = {"file": f}
    data = {"nombre_pedido": "Prueba1", "eta_fecha": "2026-10-10"}
    r = httpx.post("http://127.0.0.1:8000/api/upload/transito", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    print(r.status_code, r.text)
