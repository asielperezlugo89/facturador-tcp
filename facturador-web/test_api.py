"""Prueba integral local: registro -> activacion -> solicitud -> generacion -> PDF.
Uso: python3 test_api.py [BASE_URL]
"""
import sys, json
import urllib.request

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

print("== 1. Registro de cliente (APK) ==")
s, r = call("POST", "/api/registro", {"nombre_apellidos": "TCP Prueba Uno", "ci": "90010112345",
    "telefono": "5355000001", "direccion": "Calle Test", "cuenta_cup": "06999TEST01",
    "nit": "90010112345", "device_id": "TEST-PHONE-001", "device_info": "test"})
check("registro ok", s == 200 and r.get("ok"), r)
TOKEN = r.get("token", "")
H = {"X-Token": TOKEN, "X-Device": "TEST-PHONE-001"}

print("== 2. Estado pendiente ==")
s, r = call("POST", "/api/estado", {}, H)
check("pendiente", r.get("estado") == "pendiente", r)

print("== 3. Dispositivo ajeno bloqueado ==")
s, r = call("POST", "/api/estado", {}, {"X-Token": TOKEN, "X-Device": "OTRO-TELEFONO"})
check("bloqueo otro device", s == 403, r)

print("== 4. Activacion desde admin API ==")
s, r = call("POST", "/api/admin/login", {"username": "admin", "password": "admin123"})
check("admin login", r.get("ok"), r)
AT = {"X-Admin-Token": r.get("token", "")}
s, r = call("GET", "/api/admin/tcp", None, AT)
check("lista tcp admin", r.get("ok") and len(r.get("tcp", [])) >= 1, r)
TCP_ID = [t for t in r["tcp"] if t["telefono"] == "5355000001" or True][0]["id"] if r.get("tcp") else 0
# buscar el nuestro por codigo reciente
s, r = call("POST", f"/api/admin/activar/{TCP_ID}", {"modo": "plan"}, AT)
check("activar plan base", r.get("ok"), r)

print("== 5. Estado activo (activacion instantanea por poll) ==")
s, r = call("POST", "/api/estado", {}, H)
check("activo con 100 docs", r.get("activo") and r.get("docs") == 100, r)

print("== 6. Crear cliente final (web directa a BD via admin? usamos solicitud sin cliente) ==")
# Para probar con cliente final real, lo creamos con sqlite directo
import sqlite3
conn = sqlite3.connect("data.db")
conn.execute("INSERT INTO clientes_finales (tcp_id,empresa,cuenta_cup,agencia,nit,telefono_whatsapp,created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
             (TCP_ID, "Empresa Test SA", "06999EMP01", "BANDEC Test", "123", "5355000002"))
cli_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
conn.commit(); conn.close()
s, r = call("GET", "/api/mis-clientes", None, H)
check("mis-clientes trae 1", r.get("ok") and len(r.get("clientes", [])) >= 1, r)

print("== 7. Solicitar FACTURA ==")
s, r = call("POST", "/api/solicitar-documento", {"tipo": "factura", "cliente_final_id": cli_id,
    "contrato_no": "C-001", "items": [
        {"descripcion": "Neumático de tractor", "um": "U", "cantidad": 8, "precio": 1850000},
        {"descripcion": "Aceite hidráulico", "um": "L", "cantidad": 10, "precio": 50000}]}, H)
check("solicitud factura", r.get("ok"), r)
DOC_F = r.get("doc_id")

print("== 8. Solicitar OFERTA (fecha en blanco) ==")
s, r = call("POST", "/api/solicitar-documento", {"tipo": "oferta", "cliente_final_id": cli_id,
    "fecha_blanco": True, "items": [
        {"descripcion": "Triciclo Eléctrico", "um": "U", "cantidad": 3, "precio": 4700000}]}, H)
check("solicitud oferta", r.get("ok"), r)
DOC_O = r.get("doc_id")

print("== 9. Admin genera y envia ==")
s, r = call("POST", f"/api/admin/generar/{DOC_F}", {}, AT)
check("generar factura", r.get("ok"), r)
s, r = call("POST", f"/api/admin/generar/{DOC_O}", {}, AT)
check("generar oferta", r.get("ok"), r)

print("== 10. Descargar PDFs ==")
s, pdf = call("GET", f"/api/documentos/{DOC_F}/pdf", None, H)
check("pdf factura valido", isinstance(pdf, bytes) and pdf[:4] == b"%PDF", str(s))
open("/home/user/facturador-web/prueba_factura.pdf", "wb").write(pdf if isinstance(pdf, bytes) else b"")
s, pdf = call("GET", f"/api/documentos/{DOC_O}/pdf", None, H)
check("pdf oferta valido", isinstance(pdf, bytes) and pdf[:4] == b"%PDF", str(s))
open("/home/user/facturador-web/prueba_oferta.pdf", "wb").write(pdf if isinstance(pdf, bytes) else b"")

print("== 11. Docs descontados (100->98) ==")
s, r = call("POST", "/api/estado", {}, H)
check("saldo 98", r.get("docs") == 98, r)

print("== 12. Notificaciones cliente ==")
s, r = call("GET", "/api/notificaciones", None, H)
check("notif documento listo", any("listo" in n.get("mensaje", "") or "lista" in n.get("mensaje", "") for n in r.get("notificaciones", [])), r)

print("== 13. Recarga extra admin ==")
s, r = call("POST", f"/api/admin/activar/{TCP_ID}", {"modo": "extra"}, AT)
check("extra +50", r.get("ok"), r)
s, r = call("POST", "/api/estado", {}, H)
check("saldo 148", r.get("docs") == 148, r)

print(f"\nRESULTADO: {OK} ok, {FAIL} fallos")
sys.exit(1 if FAIL else 0)
