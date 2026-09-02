import httpx
import os

test_user = os.getenv("TEST_ADMIN_USER", "admin")
test_password = os.getenv("TEST_ADMIN_PASS")
if not test_password:
    raise RuntimeError("Define TEST_ADMIN_PASS antes de ejecutar esta prueba")

# Login to get token
r_login = httpx.post(
    "http://127.0.0.1:8000/api/auth/login",
    json={"username": test_user, "password": test_password},
)
token = r_login.json()["access_token"]

with open("data/manual_uploads/ordenes_compra/OC-2026-0047_CINTAS.xlsx", "rb") as f:
    files = {"file": f}
    data = {"nombre_pedido": "Prueba1", "eta_fecha": "2026-10-10"}
    r = httpx.post("http://127.0.0.1:8000/api/upload/transito", files=files, data=data, headers={"Authorization": f"Bearer {token}"})
    print(r.status_code, r.text)
