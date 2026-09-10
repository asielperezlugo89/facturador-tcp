"""Prueba integral API ADMIN (paridad total con la web).
Uso: python3 test_admin_api.py [BASE_URL]  (solo SQLite local; se auto-limpia)
"""
import sys, json
import urllib.request
import urllib.error

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000"
OK = 0; FAIL = 0

def call(method, path, data=None, headers=None):
    req = urllib.request.Request(BASE + path, method=method,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req) as r:
            ct = r.headers.get("Content-Type", "")
            body = r.read()
            if "application/pdf" in ct:
                return r.status, body
            return r.status, json.loads(body.decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {"http_error": e.code}

def check(nombre, cond, detalle=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK] {nombre}")
    else:
        FAIL += 1
        print(f"  [FALLO] {nombre} :: {detalle}")

print("== Admin API: login ==")
s, r = call("POST", "/api/admin/login", {"username": "admin", "password": "admin123"})
check("login", r.get("ok"), r)
H = {"X-Admin-Token": r.get("token", "")}

print("== TCP crear/editar/detalle/imagen ==")
s, r = call("POST", "/api/admin/tcp", {"nombre_apellidos": "TCP Admin Test", "telefono": "50000000"}, H)
T = r.get("tcp_id"); check("crear", r.get("ok"), r)
s, r = call("GET", f"/api/admin/tcp/{T}", None, H)
check("detalle", r.get("tcp", {}).get("nombre_apellidos") == "TCP Admin Test", r)
s, r = call("PUT", f"/api/admin/tcp/{T}", {"telefono": "51111111"}, H)
check("editar", r.get("ok"), r)
png1 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
s, r = call("POST", f"/api/admin/tcp/{T}/imagen", {"cuno_b64": png1, "firma_b64": png1}, H)
check("cuno/firma b64", r.get("ok"), r)

print("== Activar / suspender ==")
s, r = call("POST", f"/api/admin/activar/{T}", {"modo": "plan"}, H)
check("activar plan", r.get("ok"), r)
s, r = call("POST", f"/api/admin/tcp/{T}/suspender", {}, H)
check("suspender", r.get("ok"), r)
s, r = call("POST", f"/api/admin/activar/{T}", {"modo": "plan"}, H)
check("reactivar", r.get("ok"), r)

print("== Clientes finales CRUD ==")
s, r = call("POST", "/api/admin/clientes", {"tcp_id": T, "empresa": "Empresa Admin Test", "telefono_whatsapp": "5350000000"}, H)
C = r.get("cliente_id"); check("crear", r.get("ok"), r)
s, r = call("GET", f"/api/admin/clientes?tcp={T}", None, H)
check("listar filtrado", len(r.get("clientes", [])) == 1, r)
s, r = call("PUT", f"/api/admin/clientes/{C}", {"nit": "999"}, H)
check("editar", r.get("ok"), r)

print("== Documentos ==")
s, r = call("POST", "/api/admin/documentos", {"tcp_id": T, "tipo": "factura", "cliente_final_id": C,
    "items": [{"descripcion": "X", "um": "U", "cantidad": 2, "precio": 100}]}, H)
D = r.get("doc_id"); check("manual genera", r.get("ok"), r)
s, r = call("GET", "/api/admin/documentos?estado=enviado", None, H)
check("listar", any(x["id"] == D for x in r.get("documentos", [])), r)
req = urllib.request.Request(f"{BASE}/api/admin/documentos/{D}/pdf?token={H['X-Admin-Token']}")
with urllib.request.urlopen(req) as x:
    pdf = x.read()
check("pdf descarga", pdf[:4] == b"%PDF", len(pdf))
s, r = call("POST", f"/api/admin/documentos/{D}/anular", {}, H)
check("anular", r.get("ok"), r)

print("== Recargas / config / seguridad ==")
s, r = call("GET", "/api/admin/recargas", None, H)
check("recargas", r.get("ok") and len(r.get("recargas", [])) >= 1, r)
s, r = call("GET", "/api/admin/config", None, H)
check("config get", r.get("config", {}).get("precio_plan") == "1000", r)
s, r = call("PUT", "/api/admin/config", {"autogenerar": "1"}, H)
check("config put", r.get("ok"), r)
s, r = call("PUT", "/api/admin/config", {"autogenerar": "0"}, H)
s, r = call("POST", "/api/admin/password", {"username": "admin", "old": "mala", "new": "xxxx"}, H)
check("rechaza clave mala", s == 400, r)
s, r = call("GET", "/api/admin/tcp", None, {})
check("sin token 401", s == 401, r)

print("== Limpieza ==")
import sqlite3
conn = sqlite3.connect("data.db")
conn.execute("DELETE FROM documentos WHERE id=?", (D,))
conn.execute("DELETE FROM clientes_finales WHERE id=?", (C,))
conn.execute("DELETE FROM recargas WHERE tcp_id=?", (T,))
conn.execute("DELETE FROM tcp_clientes WHERE id=?", (T,))
conn.commit(); conn.close()
print("  datos de prueba eliminados")

print(f"\nRESULTADO: {OK} ok, {FAIL} fallos")
sys.exit(1 if FAIL else 0)
