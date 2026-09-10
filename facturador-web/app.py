"""Facturador TCP - Web administradora + API para APKs (Parte 1).
Compatible con Wasmer Edge: Flask + requirements.txt en la raiz.
BD: MySQL automatica en Wasmer (DB_*) o SQLite local (data.db).
"""
import datetime
import html
import io
import json
import secrets
import urllib.parse
from functools import wraps

from flask import Flask, request, session, redirect, url_for, jsonify, Response
from werkzeug.security import generate_password_hash, check_password_hash

import db
from pdfgen import generar_pdf, fmt_money, fmt_fecha

app = Flask(__name__)
app.secret_key = __import__("os").environ.get("SECRET_KEY", "tcp-facturador-secreto-local-2026")
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

# Cookies de sesion compatibles con vista previa incrustada (iframe):
# en el proxy de pruebas (https) se usa Partitioned+Secure+SameSite=None (CHIPS),
# que los navegadores aceptan dentro de iframes aunque bloqueen cookies de terceros.
# En local (http) se mantiene Lax normal.
from flask.sessions import SecureCookieSessionInterface

class PreviewSessionInterface(SecureCookieSessionInterface):
    def _is_preview(self):
        try:
            host = (request.host or "").lower()
            proto = request.headers.get("X-Forwarded-Proto", "")
        except Exception:
            return False
        return host.endswith(".e2b.app") or proto == "https"

    def get_cookie_secure(self, app):
        return True if self._is_preview() else super().get_cookie_secure(app)

    def get_cookie_samesite(self, app):
        return "None" if self._is_preview() else super().get_cookie_samesite(app)

    def get_cookie_partitioned(self, app):
        if hasattr(super(), "get_cookie_partitioned"):
            return True if self._is_preview() else super().get_cookie_partitioned(app)
        return self._is_preview()

app.session_interface = PreviewSessionInterface()

db.init_db()

# ---------- utilidades ----------
def esc(s):
    return html.escape(str(s if s is not None else ""))

def hoy():
    return datetime.date.today()

def hoy_iso():
    return hoy().strftime("%Y-%m-%d")

def cfg_int(clave, default):
    try:
        return int(db.get_config(clave, str(default)))
    except (TypeError, ValueError):
        return default

def parse_fecha(s):
    try:
        return datetime.date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None

def siguiente_codigo_tcp():
    n = db.fetchone("SELECT COUNT(*) c FROM tcp_clientes")["c"] + 1
    while db.fetchone("SELECT id FROM tcp_clientes WHERE codigo=?", (f"TCP-{n:03d}",)):
        n += 1
    return f"TCP-{n:03d}"

def siguiente_numero(tcp_id, tipo):
    pref = "F" if tipo == "factura" else "O"
    r = db.fetchone("SELECT COUNT(*) c FROM documentos WHERE tcp_id=? AND tipo=? AND estado!='anulado' AND numero!=''", (tcp_id, tipo))
    return f"{pref}-{(r['c'] + 1):04d}"

def notificar(destino, titulo, mensaje, tipo="info", extra=""):
    db.execute("INSERT INTO notificaciones (destino, titulo, mensaje, tipo, created_at, extra) VALUES (?,?,?,?,?,?)",
               (destino, titulo, mensaje, tipo, db.now_str(), extra))

def get_tcp(tcp_id):
    return db.fetchone("SELECT * FROM tcp_clientes WHERE id=?", (tcp_id,))

def get_tcp_by_token(token):
    if not token:
        return None
    return db.fetchone("SELECT * FROM tcp_clientes WHERE token=?", (token,))

def estado_vigencia(tcp):
    """Retorna dict: ok(bool), mensaje, dias_restantes, en_gracia(bool). Aplica baja automatica si procede."""
    gracia = cfg_int("dias_gracia", 15)
    if tcp["estado"] != "activo":
        return {"ok": False, "mensaje": f"Cuenta {tcp['estado']}. Contacte al administrador.", "dias": 0, "gracia": False}
    fin = parse_fecha(tcp.get("plan_fin"))
    if not fin:
        return {"ok": False, "mensaje": "Sin plan activo. Solicite una recarga.", "dias": 0, "gracia": False}
    dias = (fin - hoy()).days
    if dias >= 0:
        return {"ok": True, "mensaje": "OK", "dias": dias, "gracia": False}
    # vencido: gracia?
    if dias >= -gracia:
        return {"ok": True, "mensaje": f"Periodo vencido: esta en gracia ({dias + gracia} dias). Recargue pronto.", "dias": dias, "gracia": True}
    # mas alla de gracia -> baja automatica: docs=0 + desactivar
    db.execute("UPDATE tcp_clientes SET estado='desactivado', docs_disponibles=0 WHERE id=?", (tcp["id"],))
    notificar("admin", "Baja automatica", f"{tcp['codigo']} {tcp['nombre_apellidos']}: no recargo en {gracia} dias de gracia. Docs en 0.", "baja")
    notificar(f"tcp:{tcp['id']}", "Cuenta desactivada", "Su periodo vencio hace mas de 15 dias sin recarga. Documentos en 0. Contacte al administrador.", "baja")
    return {"ok": False, "mensaje": "Cuenta desactivada por no recargar tras el periodo de gracia.", "dias": dias, "gracia": False}

def revisar_vencimientos():
    """Barrido general (dashboard + cron)."""
    gracia = cfg_int("dias_gracia", 15)
    n = 0
    for t in db.fetchall("SELECT * FROM tcp_clientes WHERE estado='activo'"):
        fin = parse_fecha(t.get("plan_fin"))
        if fin and (hoy() - fin).days > gracia:
            db.execute("UPDATE tcp_clientes SET estado='desactivado', docs_disponibles=0 WHERE id=?", (t["id"],))
            notificar("admin", "Baja automatica", f"{t['codigo']} {t['nombre_apellidos']}: sin recarga en gracia. Docs en 0.", "baja")
            notificar(f"tcp:{t['id']}", "Cuenta desactivada", "Periodo vencido sin recarga. Documentos en 0.", "baja")
            n += 1
    return n

def activar_plan(tcp_id, admin="web"):
    tcp = get_tcp(tcp_id)
    docs_plan = cfg_int("docs_plan", 100)
    dias_plan = cfg_int("dias_plan", 30)
    precio = db.get_config("precio_plan", "1000")
    base = hoy()
    fin_actual = parse_fecha(tcp.get("plan_fin"))
    if fin_actual and fin_actual >= hoy():
        base = fin_actual  # extiende desde vencimiento si aun vigente
    fin_nuevo = base + datetime.timedelta(days=dias_plan)
    nuevos_docs = (tcp["docs_disponibles"] or 0) + docs_plan
    db.execute("UPDATE tcp_clientes SET estado='activo', docs_disponibles=?, plan_inicio=?, plan_fin=? WHERE id=?",
               (nuevos_docs, base.strftime("%Y-%m-%d"), fin_nuevo.strftime("%Y-%m-%d"), tcp_id))
    db.execute("INSERT INTO recargas (tcp_id, tipo, docs, monto, fecha, admin, nota) VALUES (?,?,?,?,?,?,?)",
               (tcp_id, "plan_base_100", docs_plan, float(precio or 0), db.now_str(), admin, f"Plan {docs_plan} docs / {dias_plan} dias"))
    notificar(f"tcp:{tcp_id}", "Cuenta activada", f"Su cuenta esta ACTIVA. {nuevos_docs} documentos disponibles hasta {fin_nuevo.strftime('%d/%m/%Y')}.", "activacion")
    notificar("admin", "Activacion", f"{tcp['codigo']} activado con plan base. Docs: {nuevos_docs}.", "activacion")
    return nuevos_docs, fin_nuevo

def recarga_extra(tcp_id, admin="web"):
    tcp = get_tcp(tcp_id)
    if tcp["estado"] == "suspendido":
        return False, "Cuenta suspendida manualmente. Active con plan base."
    fin = parse_fecha(tcp.get("plan_fin"))
    gracia = cfg_int("dias_gracia", 15)
    if tcp["estado"] == "desactivado" and (not fin or (hoy() - fin).days > gracia):
        return False, "Fuera de gracia: debe activar con PLAN BASE, no con extra."
    docs_extra = cfg_int("docs_extra", 50)
    precio = db.get_config("precio_extra", "500")
    nuevos = (tcp["docs_disponibles"] or 0) + docs_extra
    nuevo_estado = "activo" if tcp["estado"] == "activo" else "activo"
    # si estaba desactivado pero dentro de gracia, la extra lo reactiva conservando remanente
    db.execute("UPDATE tcp_clientes SET estado=?, docs_disponibles=? WHERE id=?", (nuevo_estado, nuevos, tcp_id))
    db.execute("INSERT INTO recargas (tcp_id, tipo, docs, monto, fecha, admin, nota) VALUES (?,?,?,?,?,?,?)",
               (tcp_id, "extra_50", docs_extra, float(precio or 0), db.now_str(), admin, "Recarga extra 50 docs (no extiende vigencia)"))
    notificar(f"tcp:{tcp_id}", "Recarga recibida", f"+{docs_extra} documentos. Saldo: {nuevos}.", "recarga")
    notificar("admin", "Recarga extra", f"{tcp['codigo']}: +{docs_extra} docs. Saldo: {nuevos}.", "recarga")
    return True, f"Recargados {docs_extra} documentos. Saldo: {nuevos}."

def generar_y_enviar(doc_id, admin="web"):
    doc = db.fetchone("SELECT * FROM documentos WHERE id=?", (doc_id,))
    if not doc:
        return False, "Documento no existe."
    if doc["estado"] not in ("solicitado", "generado"):
        return False, f"Documento ya esta {doc['estado']}."
    tcp = get_tcp(doc["tcp_id"])
    vig = estado_vigencia(tcp)
    if not vig["ok"]:
        return False, vig["mensaje"]
    if (tcp["docs_disponibles"] or 0) <= 0:
        return False, "Sin documentos disponibles. Requiere recarga."
    items = json.loads(doc["items_json"] or "[]")
    cli = db.fetchone("SELECT * FROM clientes_finales WHERE id=?", (doc["cliente_final_id"],)) if doc["cliente_final_id"] else None
    cli = cli or {"empresa": "", "cuenta_cup": "", "cuenta_cuc": "", "agencia": "", "codigo": "", "nit": ""}
    numero = doc["numero"]
    if not numero and not doc["numero_blanco"]:
        numero = siguiente_numero(tcp["id"], doc["tipo"])
    fecha = doc["fecha"] or ("" if doc["fecha_blanco"] else hoy_iso())
    total = sum(float(i.get("cantidad", 0)) * float(i.get("precio", 0)) for i in items)
    snap = {"tcp": {k: tcp[k] for k in ("codigo", "nombre_apellidos", "ci", "direccion", "telefono", "cuenta_cup", "agencia", "codigo_barra", "nit", "cargo")},
            "cliente": {k: cli.get(k, "") for k in ("empresa", "cuenta_cup", "cuenta_cuc", "agencia", "codigo", "nit")}}
    cuno = tcp.get("cuno_blob")
    firma = tcp.get("firma_blob")
    if isinstance(cuno, memoryview):
        cuno = cuno.tobytes()
    if isinstance(firma, memoryview):
        firma = firma.tobytes()
    pdf_bytes = generar_pdf(doc["tipo"], snap["tcp"], snap["cliente"], items, numero, fmt_fecha(fecha) if fecha else "",
                            contrato=doc["contrato_no"] or "", numero_blanco=bool(doc["numero_blanco"]),
                            fecha_blanco=bool(doc["fecha_blanco"]), cuno_bytes=cuno, firma_bytes=firma)
    db.execute("UPDATE documentos SET numero=?, fecha=?, total=?, estado='enviado', snap_json=?, pdf_blob=?, generated_at=? WHERE id=?",
               (numero, fecha, total, json.dumps(snap, ensure_ascii=False), pdf_bytes, db.now_str(), doc_id))
    db.execute("UPDATE tcp_clientes SET docs_disponibles=docs_disponibles-1 WHERE id=?", (tcp["id"],))
    saldo = (tcp["docs_disponibles"] or 0) - 1
    tipo_txt = "FACTURA" if doc["tipo"] == "factura" else "OFERTA"
    notificar(f"tcp:{tcp['id']}", "Documento listo", f"Su {tipo_txt} {numero or '(s/n)'} esta lista. Total: {fmt_money(total)}. Saldo: {saldo} docs.", "documento", extra=json.dumps({"doc_id": doc_id}))
    notificar("admin", "Documento generado", f"{tipo_txt} {numero or '(s/n)'} para {tcp['codigo']} enviada. Saldo: {saldo}.", "documento")
    return True, f"Documento {numero or '(s/n)'} generado y enviado. Saldo: {saldo}."

# ---------- auth web (cookies + respaldo sin cookies para iframes) ----------
# WEB_SESSIONS: respaldo sin cookies. Si el navegador bloquea cookies en el iframe,
# la sesion viaja como ?sk=TOKEN en la URL (ver JS en page() y _keep_sk).
WEB_SESSIONS = {}
WEB_SESSION_TTL = 8 * 3600

def _nueva_sesion_web(username):
    token = secrets.token_hex(16)
    WEB_SESSIONS[token] = (username, datetime.datetime.now().timestamp() + WEB_SESSION_TTL)
    # limpieza oportunista
    ahora = datetime.datetime.now().timestamp()
    for k in [k for k, (_, exp) in WEB_SESSIONS.items() if exp < ahora]:
        WEB_SESSIONS.pop(k, None)
    return token

def _user_por_sk(sk):
    if not sk or sk not in WEB_SESSIONS:
        return None
    username, exp = WEB_SESSIONS[sk]
    if exp < datetime.datetime.now().timestamp():
        WEB_SESSIONS.pop(sk, None)
        return None
    return username

def admin_required(f):
    @wraps(f)
    def w(*a, **kw):
        if session.get("admin"):
            return f(*a, **kw)
        sk = request.args.get("sk", "") or request.headers.get("X-Session", "")
        u = _user_por_sk(sk)
        if u:
            session["admin"] = u  # por si las cookies si funcionan
            return f(*a, **kw)
        return redirect(url_for("login"))
    return w

@app.after_request
def _keep_sk(resp):
    # conserva ?sk= en los redirects internos para no perder la sesion sin cookies
    try:
        sk = request.args.get("sk", "")
        if sk and _user_por_sk(sk) and resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc.startswith("/") and "sk=" not in loc:
                resp.headers["Location"] = loc + ("&" if "?" in loc else "?") + "sk=" + sk
    except Exception:
        pass
    return resp

def ensure_admin():
    if not db.fetchone("SELECT id FROM admin_users LIMIT 1"):
        db.execute("INSERT INTO admin_users (username, password_hash, created_at) VALUES (?,?,?)",
                   ("admin", generate_password_hash("admin123"), db.now_str()))

ensure_admin()

def admin_api_token():
    t = db.get_config("admin_api_token", "")
    if not t:
        t = secrets.token_hex(24)
        db.set_config("admin_api_token", t)
    return t

def check_admin_api():
    return request.headers.get("X-Admin-Token", "") == admin_api_token()

# ---------- estilos / layout ----------
CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,Arial,sans-serif;background:#f1f5f9;color:#0f172a;font-size:15px}
.wrap{display:flex;min-height:100vh}
.side{width:240px;background:#0f172a;color:#e2e8f0;padding:20px 12px;position:sticky;top:0;height:100vh;overflow:auto;flex-shrink:0}
.side h2{font-size:17px;padding:0 10px 16px;color:#5eead4}
.side a{display:flex;align-items:center;gap:9px;color:#cbd5e1;text-decoration:none;padding:10px;border-radius:9px;margin-bottom:3px;font-size:14.5px}
.side a:hover{background:#1e293b;color:#fff}
.side a.on{background:#0d9488;color:#fff}
.badge{background:#ef4444;color:#fff;font-size:11px;border-radius:20px;padding:1px 8px;margin-left:auto}
.badge.green{background:#10b981}.badge.amber{background:#f59e0b}
.main{flex:1;padding:22px;max-width:1180px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;flex-wrap:wrap;gap:10px}
.top h1{font-size:22px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.card{background:#fff;border-radius:14px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card .n{font-size:26px;font-weight:800;color:#0d9488}
.card .l{font-size:13px;color:#64748b}
.box{background:#fff;border-radius:14px;padding:18px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:18px}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:9px 8px;border-bottom:1px solid #e2e8f0;text-align:left;vertical-align:top}
th{background:#f8fafc;color:#475569;font-size:13px;text-transform:uppercase}
tr:hover td{background:#f8fafc}
.btn{display:inline-block;background:#0d9488;color:#fff;border:none;padding:9px 16px;border-radius:9px;text-decoration:none;cursor:pointer;font-size:14px;margin:2px}
.btn:hover{background:#0f766e}
.btn.gray{background:#64748b}.btn.gray:hover{background:#475569}
.btn.red{background:#ef4444}.btn.red:hover{background:#dc2626}
.btn.amber{background:#f59e0b;color:#111}.btn.blue{background:#2563eb}
.btn.sm{padding:5px 10px;font-size:13px}
input,select,textarea{padding:9px 11px;border:1px solid #cbd5e1;border-radius:9px;font-size:14px;width:100%;margin:3px 0 10px}
label{font-size:13.5px;font-weight:600;color:#334155}
.frow{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px}
.msg{padding:12px 15px;border-radius:10px;margin-bottom:14px}
.msg.ok{background:#d1fae5;color:#065f46}.msg.err{background:#fee2e2;color:#991b1b}.msg.warn{background:#fef3c7;color:#92400e}
.pill{display:inline-block;padding:2px 11px;border-radius:20px;font-size:12.5px;font-weight:700}
.p-activo,.p-enviado{background:#d1fae5;color:#065f46}.p-pendiente,.p-solicitado{background:#fef3c7;color:#92400e}
.p-desactivado,.p-suspendido,.p-anulado{background:#fee2e2;color:#991b1b}.p-generado{background:#dbeafe;color:#1e40af}
.login{max-width:400px;margin:8vh auto;background:#fff;padding:30px;border-radius:16px;box-shadow:0 4px 20px rgba(0,0,0,.1)}
.login h1{color:#0d9488;margin-bottom:6px}.login p{color:#64748b;margin-bottom:16px}
pre.api{background:#0f172a;color:#a5f3fc;padding:14px;border-radius:10px;overflow:auto;font-size:12.5px}
.itemrow{display:grid;grid-template-columns:1fr 70px 90px 130px 40px;gap:6px;align-items:end}
@media(max-width:800px){.side{width:100%;height:auto;position:static}.wrap{flex-direction:column}.itemrow{grid-template-columns:1fr 60px 70px 100px 35px}}
"""

SK_JS = """<script>
/* Propaga ?sk= (sesion sin cookies) por enlaces y formularios */
(function(){try{
var m=location.search.match(/[?&]sk=([a-f0-9]+)/);
var sk=m?m[1]:sessionStorage.getItem('sk');
if(m){try{sessionStorage.setItem('sk',sk);}catch(e){}}
if(!sk){return;}
document.querySelectorAll('a[href]').forEach(function(a){
  var h=a.getAttribute('href');
  if(h && h.charAt(0)==='/' && h.indexOf('sk=')<0){
    a.setAttribute('href',h+(h.indexOf('?')>=0?'&':'?')+'sk='+sk);}});
document.querySelectorAll('form').forEach(function(f){
  var a=f.getAttribute('action')||location.pathname;
  if(a.charAt(0)==='/' && a.indexOf('sk=')<0){
    f.setAttribute('action',a+(a.indexOf('?')>=0?'&':'?')+'sk='+sk);}});
}catch(e){}})();
</script>"""


def page(title, content, active="", msg=None):
    m = ""
    if msg:
        m = f'<div class="msg {esc(msg[0])}">{esc(msg[1])}</div>'
    sol = db.fetchone("SELECT COUNT(*) c FROM documentos WHERE estado='solicitado'")["c"]
    pen = db.fetchone("SELECT COUNT(*) c FROM tcp_clientes WHERE estado='pendiente'")["c"]
    na = db.fetchone("SELECT COUNT(*) c FROM notificaciones WHERE destino='admin' AND leida=0")["c"]
    def nav(href, label, key, badge=0):
        return f'<a href="{href}" class="{"on" if active==key else ""}">{label}{f"<span class=badge>{badge}</span>" if badge else ""}</a>'
    sidebar = f"""
    <h2>📄 {esc(db.get_config('nombre_sistema','Facturador TCP'))}</h2>
    {nav('/','🏠 Panel','panel')}
    {nav('/tcp','👥 TCP Clientes','tcp',pen)}
    {nav('/documentos','📑 Documentos','doc',sol)}
    {nav('/recargas','💳 Recargas','rec')}
    {nav('/notificaciones','🔔 Notificaciones','not',na)}
    {nav('/config','⚙️ Config / API','cfg')}
    {nav('/logout','🚪 Salir ('+esc(session.get('admin',''))+')','')}
    """
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>
<style>{CSS}</style></head><body><div class="wrap"><div class="side">{sidebar}</div>
<div class="main"><div class="top"><h1>{esc(title)}</h1></div>{m}{content}</div></div>
{SK_JS}
</body></html>"""

# ---------- web: login ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    ensure_admin()
    err = ""
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "")
        r = db.fetchone("SELECT * FROM admin_users WHERE username=?", (u,))
        if r and check_password_hash(r["password_hash"], p):
            session["admin"] = u
            sk = _nueva_sesion_web(u)
            return redirect(url_for("panel", sk=sk))
        err = "Usuario o clave incorrectos."
    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Entrar</title><style>{CSS}</style></head><body><div class="login">
<h1>📄 Facturador TCP</h1><p>Panel administrador</p>
{f'<div class="msg err">{esc(err)}</div>' if err else ''}
<form method="post"><label>Usuario</label><input name="username" required>
<label>Clave</label><input type="password" name="password" required>
<button class="btn" style="width:100%">Entrar</button></form></div></body></html>"""

@app.route("/logout")
def logout():
    WEB_SESSIONS.pop(request.args.get("sk", ""), None)
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@admin_required
def panel():
    revisar_vencimientos()
    n_tcp = db.fetchone("SELECT COUNT(*) c FROM tcp_clientes")["c"]
    n_act = db.fetchone("SELECT COUNT(*) c FROM tcp_clientes WHERE estado='activo'")["c"]
    n_pen = db.fetchone("SELECT COUNT(*) c FROM tcp_clientes WHERE estado='pendiente'")["c"]
    n_sol = db.fetchone("SELECT COUNT(*) c FROM documentos WHERE estado='solicitado'")["c"]
    n_doc = db.fetchone("SELECT COUNT(*) c FROM documentos WHERE estado='enviado'")["c"]
    rec = db.fetchone("SELECT COALESCE(SUM(monto),0) s FROM recargas")["s"]
    docs = db.fetchall("SELECT d.*, t.codigo FROM documentos d JOIN tcp_clientes t ON t.id=d.tcp_id ORDER BY d.id DESC LIMIT 8")
    rows = "".join(f"<tr><td>{esc(d['id'])}</td><td>{esc(d['tipo'])}</td><td>{esc(d['numero'] or '(s/n)')}</td><td>{esc(d['codigo'])}</td><td><span class='pill p-{esc(d['estado'])}'>{esc(d['estado'])}</span></td><td>{fmt_money(d['total'])}</td></tr>" for d in docs)
    demo = ""
    if n_tcp == 0:
        demo = "<div class='box'><b>Sin datos.</b> Puede <a class='btn sm' href='/demo'>cargar demo (TCP Christian + clientes)</a> para probar.</div>"
    c = f"""{demo}
    <div class="cards">
      <div class="card"><div class="n">{n_tcp}</div><div class="l">TCP registrados</div></div>
      <div class="card"><div class="n">{n_act}</div><div class="l">Activos</div></div>
      <div class="card"><div class="n">{n_pen}</div><div class="l">Pendientes</div></div>
      <div class="card"><div class="n">{n_sol}</div><div class="l">Solicitudes</div></div>
      <div class="card"><div class="n">{n_doc}</div><div class="l">Docs enviados</div></div>
      <div class="card"><div class="n">{fmt_money(rec)}</div><div class="l">Cobrado (CUP)</div></div>
    </div>
    <div class="box"><h3>📱 Apps (simuladores)</h3><p><a class="btn" href="/simulador">📱 Sim APK cliente</a> <a class="btn blue" href="/simulador-admin">🛡️ Sim App admin</a></p><p><small>Cada app por separado para revisarlas. El Sim cliente también se abre desde la ficha de cada TCP con sus datos cargados.</small></p></div>
    <div class="box"><h3>Últimos documentos</h3><table><tr><th>ID</th><th>Tipo</th><th>No.</th><th>TCP</th><th>Estado</th><th>Total</th></tr>{rows or '<tr><td colspan=6>Ninguno</td></tr>'}</table></div>"""
    return page("Panel", c, "panel", _flash())

def _flash():
    m = session.pop("flash", None)
    return tuple(m) if m else None

def _set_flash(tipo, txt):
    session["flash"] = [tipo, txt]

@app.route("/demo")
@admin_required
def demo():
    if db.fetchone("SELECT COUNT(*) c FROM tcp_clientes")["c"]:
        _set_flash("warn", "Ya hay TCPs, demo no cargada.")
        return redirect(url_for("panel"))
    token = secrets.token_hex(16)
    tcp_id = db.execute("""INSERT INTO tcp_clientes (codigo,nombre_apellidos,ci,direccion,telefono,cuenta_cup,agencia,codigo_barra,nit,cargo,token,estado,docs_disponibles,created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      ("TCP-001", "Christian Randy Sedeño Hernández", "02060276164",
       "Calle 2da # s/n e/ Calle C y Calle B, Reparto San Antonio Minas, Camagüey",
       "5XXXXXXX", "0699970017272115", "5761 BANDEC Moralito 211 Minas, Camagüey.",
       "9167 - 4602 - 0206 - 4003", "02060276164", "TCP", token, "pendiente", 0, db.now_str()))
    for emp, cup, cuc, ag, cod, nit, tel in [
        ("Empresa Agropecuaria Minas", "06990XXXXXXX01", "", "BANDEC Minas", "AG-01", "12345678901", "535XXXXXX1"),
        ("UBPC San Antonio", "06990XXXXXXX02", "", "BANDEC Minas", "UB-02", "12345678902", "535XXXXXX2"),
    ]:
        db.execute("INSERT INTO clientes_finales (tcp_id,empresa,cuenta_cup,cuenta_cuc,agencia,codigo,nit,telefono_whatsapp,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (tcp_id, emp, cup, cuc, ag, cod, nit, tel, db.now_str()))
    notificar("admin", "Demo cargada", "TCP-001 Christian + 2 clientes finales listos. Actívelo con plan base.", "info")
    _set_flash("ok", "Demo cargada: TCP-001 pendiente. Actívelo en TCP Clientes.")
    return redirect(url_for("tcp_list"))

# ---------- web: TCP ----------
@app.route("/tcp")
@admin_required
def tcp_list():
    revisar_vencimientos()
    rows = db.fetchall("SELECT * FROM tcp_clientes ORDER BY id DESC")
    tr = ""
    for t in rows:
        fin = fmt_fecha(t["plan_fin"]) if t.get("plan_fin") else "-"
        tr += f"""<tr><td><b>{esc(t['codigo'])}</b></td><td>{esc(t['nombre_apellidos'])}<br><small>{esc(t['telefono'])} {esc(t['ci'])}</small></td>
        <td><span class='pill p-{esc(t['estado'])}'>{esc(t['estado'])}</span></td><td><b>{t['docs_disponibles']}</b></td><td>{fin}</td>
        <td><a class="btn sm" href="/tcp/{t['id']}">Abrir</a></td></tr>"""
    c = f"""<div class="box"><a class="btn" href="/tcp/nuevo">+ Nuevo TCP</a>
    <table style="margin-top:12px"><tr><th>Código</th><th>Nombre</th><th>Estado</th><th>Docs</th><th>Vence</th><th></th></tr>{tr or '<tr><td colspan=6>Ninguno</td></tr>'}</table></div>"""
    return page("TCP Clientes", c, "tcp", _flash())

@app.route("/tcp/nuevo", methods=["GET", "POST"])
@admin_required
def tcp_nuevo():
    if request.method == "POST":
        f = request.form
        if not f.get("nombre_apellidos", "").strip():
            return page("Nuevo TCP", "<div class='box'>Falta el nombre. <a href='/tcp/nuevo'>Volver</a></div>", "tcp")
        cuno = request.files.get("cuno")
        firma = request.files.get("firma")
        tcp_id = db.execute("""INSERT INTO tcp_clientes (codigo,nombre_apellidos,ci,direccion,telefono,email,cuenta_cup,agencia,codigo_barra,nit,cargo,token,estado,docs_disponibles,created_at,cuno_blob,firma_blob,cuno_filename,firma_filename)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
          (siguiente_codigo_tcp(), f.get("nombre_apellidos").strip(), f.get("ci","").strip(), f.get("direccion","").strip(),
           f.get("telefono","").strip(), f.get("email","").strip(), f.get("cuenta_cup","").strip(), f.get("agencia","").strip(),
           f.get("codigo_barra","").strip(), f.get("nit","").strip(), f.get("cargo","TCP").strip() or "TCP",
           secrets.token_hex(16), "pendiente", 0, db.now_str(),
           cuno.read() if cuno and cuno.filename else None, firma.read() if firma and firma.filename else None,
           cuno.filename if cuno and cuno.filename else "", firma.filename if firma and firma.filename else ""))
        notificar("admin", "TCP creado", f"{f.get('nombre_apellidos')} registrado desde web, pendiente de activar.", "info")
        _set_flash("ok", "TCP creado (pendiente). Actívelo con plan base.")
        return redirect(url_for("tcp_ver", tcp_id=tcp_id))
    c = """<div class="box"><form method="post" enctype="multipart/form-data"><div class="frow">
    <div><label>Nombre y apellidos *</label><input name="nombre_apellidos" required></div>
    <div><label>Carné identidad</label><input name="ci"></div></div>
    <label>Dirección</label><input name="direccion">
    <div class="frow"><div><label>Teléfono</label><input name="telefono"></div>
    <div><label>Email</label><input name="email"></div>
    <div><label>Cargo</label><input name="cargo" value="TCP"></div></div>
    <div class="frow"><div><label>Cuenta CUP</label><input name="cuenta_cup"></div>
    <div><label>Agencia bancaria</label><input name="agencia"></div></div>
    <div class="frow"><div><label>Código de barra</label><input name="codigo_barra"></div>
    <div><label>NIT</label><input name="nit"></div></div>
    <div class="frow"><div><label>Cuño (PNG)</label><input type="file" name="cuno" accept="image/*"></div>
    <div><label>Firma (PNG)</label><input type="file" name="firma" accept="image/*"></div></div>
    <button class="btn">Guardar</button> <a class="btn gray" href="/tcp">Volver</a></form></div>"""
    return page("Nuevo TCP", c, "tcp")

@app.route("/tcp/<int:tcp_id>")
@admin_required
def tcp_ver(tcp_id):
    t = get_tcp(tcp_id)
    if not t:
        return redirect(url_for("tcp_list"))
    vig = estado_vigencia(t) if t["estado"] == "activo" else None
    clis = db.fetchall("SELECT * FROM clientes_finales WHERE tcp_id=? ORDER BY empresa", (tcp_id,))
    docs = db.fetchall("SELECT * FROM documentos WHERE tcp_id=? ORDER BY id DESC LIMIT 15", (tcp_id,))
    recs = db.fetchall("SELECT * FROM recargas WHERE tcp_id=? ORDER BY id DESC LIMIT 10", (tcp_id,))
    cli_rows = "".join(f"<tr><td>{esc(c['empresa'])}</td><td>{esc(c['telefono_whatsapp'] or '-')}</td><td><a class='btn sm gray' href='/clientes/{c['id']}/editar'>Editar</a></td></tr>" for c in clis)
    doc_rows = "".join(f"<tr><td>{d['id']}</td><td>{esc(d['tipo'])}</td><td>{esc(d['numero'] or '(s/n)')}</td><td><span class='pill p-{esc(d['estado'])}'>{esc(d['estado'])}</span></td><td>{fmt_money(d['total'])}</td><td><a class='btn sm' href='/documentos/{d['id']}'>Abrir</a></td></tr>" for d in docs)
    rec_rows = "".join(f"<tr><td>{esc(r['fecha'])}</td><td>{esc(r['tipo'])}</td><td>{r['docs']}</td><td>{fmt_money(r['monto'])}</td><td>{esc(r['nota'])}</td></tr>" for r in recs)
    c = f"""
    <div class="box"><b>{esc(t['codigo'])}</b> — {esc(t['nombre_apellidos'])} <span class='pill p-{esc(t['estado'])}'>{esc(t['estado'])}</span>
    <p style="margin-top:8px">CI: {esc(t['ci'])} · NIT: {esc(t['nit'])} · Tel: {esc(t['telefono'])}<br>
    Dir: {esc(t['direccion'])}<br>Cuenta CUP: {esc(t['cuenta_cup'])} · Agencia: {esc(t['agencia'])}<br>
    <b>Docs disponibles: {t['docs_disponibles']}</b> · Plan: {esc(t['plan_inicio'] or '-')} → {esc(t['plan_fin'] or '-')}
    {('<br><span class="pill p-solicitado">'+esc(vig['mensaje'])+'</span>') if vig and vig.get('gracia') else ''}
    <br><small>Token API: <code>{esc(t['token'])}</code> · Dispositivo: {esc(t['device_id'] or '(sin vincular)')}</small>
    <br><small>Cuño: {esc(t['cuno_filename'] or '—')} · Firma: {esc(t['firma_filename'] or '—')}</small></p>
    <p style="margin-top:10px">
      <a class="btn sm" href="/tcp/{tcp_id}/activar" onclick="return confirm('Activar con PLAN BASE ({cfg_int('docs_plan',100)} docs)?')">⚡ Activar plan base</a>
      <a class="btn sm amber" href="/tcp/{tcp_id}/extra" onclick="return confirm('Recargar EXTRA ({cfg_int('docs_extra',50)} docs)?')">+ Recarga extra</a>
      <a class="btn sm gray" href="/tcp/{tcp_id}/editar">✏️ Editar / cuño-firma</a>
      <a class="btn sm gray" href="/clientes/nuevo?tcp={tcp_id}">+ Cliente final</a>
      <a class="btn sm gray" href="/documentos/nuevo?tcp={tcp_id}">+ Documento manual</a>
      <a class="btn sm red" href="/tcp/{tcp_id}/suspender" onclick="return confirm('¿Suspender cuenta?')">Suspender</a>
      <a class="btn sm blue" href="/simulador?dev={esc(t['device_id'] or '')}&tok={esc(t['token'])}">📱 Abrir en simulador</a> <a class="btn sm gray" href="/tcp/{tcp_id}">🔄</a>
    </p></div>
    <div class="box"><h3>Clientes finales ({len(clis)})</h3><table><tr><th>Empresa</th><th>WhatsApp</th><th></th></tr>{cli_rows or '<tr><td colspan=3>Ninguno</td></tr>'}</table></div>
    <div class="box"><h3>Documentos recientes</h3><table><tr><th>ID</th><th>Tipo</th><th>No.</th><th>Estado</th><th>Total</th><th></th></tr>{doc_rows or '<tr><td colspan=6>Ninguno</td></tr>'}</table></div>
    <div class="box"><h3>Recargas</h3><table><tr><th>Fecha</th><th>Tipo</th><th>Docs</th><th>Monto</th><th>Nota</th></tr>{rec_rows or '<tr><td colspan=5>Ninguna</td></tr>'}</table></div>"""
    return page(f"TCP {t['codigo']}", c, "tcp", _flash())

@app.route("/tcp/<int:tcp_id>/editar", methods=["GET", "POST"])
@admin_required
def tcp_editar(tcp_id):
    t = get_tcp(tcp_id)
    if not t:
        return redirect(url_for("tcp_list"))
    if request.method == "POST":
        f = request.form
        cuno = request.files.get("cuno")
        firma = request.files.get("firma")
        db.execute("""UPDATE tcp_clientes SET nombre_apellidos=?,ci=?,direccion=?,telefono=?,email=?,cuenta_cup=?,agencia=?,codigo_barra=?,nit=?,cargo=? WHERE id=?""",
                   (f.get("nombre_apellidos","").strip(), f.get("ci",""), f.get("direccion",""), f.get("telefono",""), f.get("email",""),
                    f.get("cuenta_cup",""), f.get("agencia",""), f.get("codigo_barra",""), f.get("nit",""), f.get("cargo","TCP"), tcp_id))
        if cuno and cuno.filename:
            db.execute("UPDATE tcp_clientes SET cuno_blob=?, cuno_filename=? WHERE id=?", (cuno.read(), cuno.filename, tcp_id))
        if firma and firma.filename:
            db.execute("UPDATE tcp_clientes SET firma_blob=?, firma_filename=? WHERE id=?", (firma.read(), firma.filename, tcp_id))
        _set_flash("ok", "TCP actualizado.")
        return redirect(url_for("tcp_ver", tcp_id=tcp_id))
    c = f"""<div class="box"><form method="post" enctype="multipart/form-data"><div class="frow">
    <div><label>Nombre y apellidos</label><input name="nombre_apellidos" value="{esc(t['nombre_apellidos'])}"></div>
    <div><label>Carné</label><input name="ci" value="{esc(t['ci'])}"></div></div>
    <label>Dirección</label><input name="direccion" value="{esc(t['direccion'])}">
    <div class="frow"><div><label>Teléfono</label><input name="telefono" value="{esc(t['telefono'])}"></div>
    <div><label>Email</label><input name="email" value="{esc(t['email'])}"></div>
    <div><label>Cargo</label><input name="cargo" value="{esc(t['cargo'])}"></div></div>
    <div class="frow"><div><label>Cuenta CUP</label><input name="cuenta_cup" value="{esc(t['cuenta_cup'])}"></div>
    <div><label>Agencia</label><input name="agencia" value="{esc(t['agencia'])}"></div></div>
    <div class="frow"><div><label>Código barra</label><input name="codigo_barra" value="{esc(t['codigo_barra'])}"></div>
    <div><label>NIT</label><input name="nit" value="{esc(t['nit'])}"></div></div>
    <div class="frow"><div><label>Cuño PNG (actual: {esc(t['cuno_filename'] or '—')})</label><input type="file" name="cuno" accept="image/*"></div>
    <div><label>Firma PNG (actual: {esc(t['firma_filename'] or '—')})</label><input type="file" name="firma" accept="image/*"></div></div>
    <button class="btn">Guardar</button> <a class="btn gray" href="/tcp/{tcp_id}">Volver</a></form></div>"""
    return page(f"Editar {t['codigo']}", c, "tcp")

@app.route("/tcp/<int:tcp_id>/activar")
@admin_required
def tcp_activar(tcp_id):
    docs, fin = activar_plan(tcp_id, session.get("admin", "web"))
    _set_flash("ok", f"Activado: {docs} docs hasta {fin.strftime('%d/%m/%Y')}.")
    return redirect(url_for("tcp_ver", tcp_id=tcp_id))

@app.route("/tcp/<int:tcp_id>/extra")
@admin_required
def tcp_extra(tcp_id):
    ok, msg = recarga_extra(tcp_id, session.get("admin", "web"))
    _set_flash("ok" if ok else "err", msg)
    return redirect(url_for("tcp_ver", tcp_id=tcp_id))

@app.route("/tcp/<int:tcp_id>/suspender")
@admin_required
def tcp_suspender(tcp_id):
    t = get_tcp(tcp_id)
    db.execute("UPDATE tcp_clientes SET estado='suspendido' WHERE id=?", (tcp_id,))
    notificar(f"tcp:{tcp_id}", "Cuenta suspendida", "Su cuenta fue suspendida por el administrador.", "baja")
    notificar("admin", "Suspensión", f"{t['codigo']} suspendido.", "baja")
    _set_flash("warn", "Cuenta suspendida.")
    return redirect(url_for("tcp_ver", tcp_id=tcp_id))

# ---------- web: clientes finales ----------
@app.route("/clientes")
@admin_required
def cli_list():
    tcp_f = request.args.get("tcp", "")
    q = "SELECT c.*, t.codigo FROM clientes_finales c JOIN tcp_clientes t ON t.id=c.tcp_id"
    p = ()
    if tcp_f:
        q += " WHERE c.tcp_id=?"
        p = (tcp_f,)
    q += " ORDER BY c.id DESC"
    rows = db.fetchall(q, p)
    tr = "".join(f"<tr><td>{esc(c['codigo'])}</td><td>{esc(c['empresa'])}</td><td>{esc(c['telefono_whatsapp'] or '-')}</td><td><a class='btn sm gray' href='/clientes/{c['id']}/editar'>Editar</a> <a class='btn sm red' href='/clientes/{c['id']}/eliminar' onclick='return confirm(\"¿Eliminar?\")'>X</a></td></tr>" for c in rows)
    c = f"""<div class="box"><a class="btn" href="/clientes/nuevo">+ Nuevo cliente final</a>
    <table style="margin-top:12px"><tr><th>TCP</th><th>Empresa</th><th>WhatsApp</th><th></th></tr>{tr or '<tr><td colspan=4>Ninguno</td></tr>'}</table></div>"""
    return page("Clientes finales", c, "cli", _flash())

@app.route("/clientes/nuevo", methods=["GET", "POST"])
@admin_required
def cli_nuevo():
    tcps = db.fetchall("SELECT id, codigo, nombre_apellidos FROM tcp_clientes ORDER BY codigo")
    if not tcps:
        _set_flash("warn", "Primero cree un TCP.")
        return redirect(url_for("tcp_list"))
    if request.method == "POST":
        f = request.form
        db.execute("INSERT INTO clientes_finales (tcp_id,empresa,cuenta_cup,cuenta_cuc,agencia,codigo,nit,telefono_whatsapp,direccion,notas,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   (f.get("tcp_id"), f.get("empresa","").strip(), f.get("cuenta_cup",""), f.get("cuenta_cuc",""), f.get("agencia",""),
                    f.get("codigo",""), f.get("nit",""), f.get("telefono_whatsapp",""), f.get("direccion",""), f.get("notas",""), db.now_str()))
        _set_flash("ok", "Cliente final creado.")
        return redirect(url_for("cli_list"))
    pretcp = request.args.get("tcp", "")
    opts = "".join(f"<option value='{t['id']}' {'selected' if str(t['id'])==pretcp else ''}>{esc(t['codigo'])} — {esc(t['nombre_apellidos'])}</option>" for t in tcps)
    c = f"""<div class="box"><form method="post"><label>TCP dueño</label><select name="tcp_id">{opts}</select>
    <label>Empresa *</label><input name="empresa" required>
    <div class="frow"><div><label>Cuenta CUP</label><input name="cuenta_cup"></div><div><label>Cuenta CUC</label><input name="cuenta_cuc"></div></div>
    <div class="frow"><div><label>Agencia</label><input name="agencia"></div><div><label>Código</label><input name="codigo"></div><div><label>NIT</label><input name="nit"></div></div>
    <div class="frow"><div><label>WhatsApp (con código país, ej 535XXXXXXX)</label><input name="telefono_whatsapp"></div><div><label>Dirección</label><input name="direccion"></div></div>
    <label>Notas</label><input name="notas">
    <button class="btn">Guardar</button> <a class="btn gray" href="/clientes">Volver</a></form></div>"""
    return page("Nuevo cliente final", c, "cli")

@app.route("/clientes/<int:cid>/editar", methods=["GET", "POST"])
@admin_required
def cli_editar(cid):
    c0 = db.fetchone("SELECT * FROM clientes_finales WHERE id=?", (cid,))
    if not c0:
        return redirect(url_for("cli_list"))
    if request.method == "POST":
        f = request.form
        db.execute("UPDATE clientes_finales SET empresa=?,cuenta_cup=?,cuenta_cuc=?,agencia=?,codigo=?,nit=?,telefono_whatsapp=?,direccion=?,notas=? WHERE id=?",
                   (f.get("empresa",""), f.get("cuenta_cup",""), f.get("cuenta_cuc",""), f.get("agencia",""), f.get("codigo",""),
                    f.get("nit",""), f.get("telefono_whatsapp",""), f.get("direccion",""), f.get("notas",""), cid))
        _set_flash("ok", "Actualizado.")
        return redirect(url_for("cli_list"))
    c = f"""<div class="box"><form method="post">
    <label>Empresa</label><input name="empresa" value="{esc(c0['empresa'])}">
    <div class="frow"><div><label>Cuenta CUP</label><input name="cuenta_cup" value="{esc(c0['cuenta_cup'])}"></div><div><label>Cuenta CUC</label><input name="cuenta_cuc" value="{esc(c0['cuenta_cuc'])}"></div></div>
    <div class="frow"><div><label>Agencia</label><input name="agencia" value="{esc(c0['agencia'])}"></div><div><label>Código</label><input name="codigo" value="{esc(c0['codigo'])}"></div><div><label>NIT</label><input name="nit" value="{esc(c0['nit'])}"></div></div>
    <div class="frow"><div><label>WhatsApp</label><input name="telefono_whatsapp" value="{esc(c0['telefono_whatsapp'])}"></div><div><label>Dirección</label><input name="direccion" value="{esc(c0['direccion'])}"></div></div>
    <label>Notas</label><input name="notas" value="{esc(c0['notas'])}">
    <button class="btn">Guardar</button> <a class="btn gray" href="/clientes">Volver</a></form></div>"""
    return page("Editar cliente final", c, "cli")

@app.route("/clientes/<int:cid>/eliminar")
@admin_required
def cli_eliminar(cid):
    db.execute("DELETE FROM clientes_finales WHERE id=?", (cid,))
    _set_flash("ok", "Eliminado.")
    return redirect(url_for("cli_list"))

# ---------- web: documentos ----------
@app.route("/documentos")
@admin_required
def doc_list():
    est = request.args.get("estado", "")
    q = "SELECT d.*, t.codigo FROM documentos d JOIN tcp_clientes t ON t.id=d.tcp_id"
    p = ()
    if est:
        q += " WHERE d.estado=?"
        p = (est,)
    q += " ORDER BY d.id DESC LIMIT 100"
    rows = db.fetchall(q, p)
    tr = ""
    for d in rows:
        pdf = f"<a class='btn sm gray' href='/documentos/{d['id']}/pdf'>PDF</a>" if d["estado"] in ("generado", "enviado") else ""
        gen = f"<a class='btn sm' href='/documentos/{d['id']}/generar'>Generar y enviar</a>" if d["estado"] == "solicitado" else ""
        tr += f"<tr><td>{d['id']}</td><td>{esc(d['tipo'])}</td><td>{esc(d['numero'] or '(s/n)')}</td><td>{esc(d['codigo'])}</td><td><span class='pill p-{esc(d['estado'])}'>{esc(d['estado'])}</span></td><td>{fmt_money(d['total'])}</td><td><a class='btn sm gray' href='/documentos/{d['id']}'>Abrir</a> {gen} {pdf}</td></tr>"
    c = f"""<div class="box"><a class="btn" href="/documentos/nuevo">+ Documento manual</a>
    <a class="btn gray" href="/documentos">Todos</a> <a class="btn amber" href="/documentos?estado=solicitado">Solicitudes</a>
    <table style="margin-top:12px"><tr><th>ID</th><th>Tipo</th><th>No.</th><th>TCP</th><th>Estado</th><th>Total</th><th></th></tr>{tr or '<tr><td colspan=7>Ninguno</td></tr>'}</table></div>"""
    return page("Documentos", c, "doc", _flash())

@app.route("/documentos/nuevo", methods=["GET", "POST"])
@admin_required
def doc_nuevo():
    tcps = db.fetchall("SELECT id, codigo, nombre_apellidos FROM tcp_clientes WHERE estado='activo' ORDER BY codigo")
    if request.method == "POST":
        f = request.form
        tcp_id = int(f.get("tcp_id", 0))
        cli_id = int(f.get("cliente_final_id", 0) or 0)
        tipo = f.get("tipo", "factura")
        items = []
        for i in range(12):
            desc = f.get(f"desc{i}", "").strip()
            if desc:
                try:
                    items.append({"descripcion": desc, "um": f.get(f"um{i}", "U") or "U",
                                  "cantidad": float(f.get(f"cant{i}", 0) or 0), "precio": float(f.get(f"precio{i}", 0) or 0)})
                except ValueError:
                    pass
        if not items:
            _set_flash("err", "Agregue al menos un artículo.")
            return redirect(url_for("doc_nuevo"))
        doc_id = db.execute("INSERT INTO documentos (numero,tipo,tcp_id,cliente_final_id,contrato_no,fecha,numero_blanco,fecha_blanco,items_json,total,estado,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                            ("", tipo, tcp_id, cli_id, f.get("contrato_no",""), f.get("fecha",""),
                             1 if f.get("numero_blanco") else 0, 1 if (f.get("fecha_blanco") or not f.get("fecha","")) else 0,
                             json.dumps(items, ensure_ascii=False), 0, "solicitado", db.now_str()))
        ok, msg = generar_y_enviar(doc_id, session.get("admin", "web"))
        _set_flash("ok" if ok else "err", msg)
        return redirect(url_for("doc_ver", doc_id=doc_id))
    if not tcps:
        return page("Nuevo documento", "<div class='box'>No hay TCP activos. <a href='/tcp'>Activar uno</a></div>", "doc")
    opts = "".join(f"<option value='{t['id']}'>{esc(t['codigo'])} — {esc(t['nombre_apellidos'])}</option>" for t in tcps)
    pretcp = request.args.get("tcp", "")
    if pretcp:
        opts = "".join(f"<option value='{t['id']}' {'selected' if str(t['id'])==pretcp else ''}>{esc(t['codigo'])} — {esc(t['nombre_apellidos'])}</option>" for t in tcps)
    clis = db.fetchall("SELECT id, tcp_id, empresa FROM clientes_finales ORDER BY empresa")
    cli_json = json.dumps([dict(c) for c in clis], ensure_ascii=False)
    item_rows = ""
    for i in range(5):
        item_rows += f"""<div class="itemrow"><div><input name="desc{i}" placeholder="Descripción"></div><div><input name="um{i}" value="U"></div>
        <div><input name="cant{i}" type="number" step="any" placeholder="Cant"></div><div><input name="precio{i}" type="number" step="any" placeholder="Precio"></div><div></div></div>"""
    c = f"""<div class="box"><form method="post">
    <div class="frow"><div><label>TCP</label><select name="tcp_id" id="tcp_sel" onchange="filtra()">{opts}</select></div>
    <div><label>Tipo</label><select name="tipo"><option value="factura">FACTURA DE VENTA</option><option value="oferta">OFERTA COMERCIAL</option></select></div></div>
    <div class="frow"><div><label>Cliente final</label><select name="cliente_final_id" id="cli_sel"></select></div>
    <div><label>Contrato No. (factura)</label><input name="contrato_no"></div>
    <div><label>Fecha (vacía = hoy)</label><input name="fecha" type="date" value="{hoy_iso()}"></div></div>
    <p><label><input type="checkbox" name="numero_blanco" style="width:auto"> Dejar número en blanco (___)</label> &nbsp;
    <label><input type="checkbox" name="fecha_blanco" style="width:auto"> Fecha en blanco (__/__/____)</label></p>
    <h4>Artículos (solo filas necesarias)</h4>
    <div class="itemrow" style="font-weight:700"><div>Descripción</div><div>U/M</div><div>Cant.</div><div>Precio</div><div></div></div>
    {item_rows}
    <button class="btn">Generar y enviar (descuenta 1 doc)</button></form></div>
    <script>var CLIS={cli_json};
    function filtra(){{var t=document.getElementById('tcp_sel').value;var s=document.getElementById('cli_sel');s.innerHTML='<option value=0>— Sin cliente / llenar a mano —</option>';
    CLIS.forEach(function(c){{if(String(c.tcp_id)===String(t)){{var o=document.createElement('option');o.value=c.id;o.textContent=c.empresa;s.appendChild(o);}}}});}}
    filtra();</script>"""
    return page("Nuevo documento", c, "doc")

@app.route("/documentos/<int:doc_id>")
@admin_required
def doc_ver(doc_id):
    d = db.fetchone("SELECT d.*, t.codigo, t.nombre_apellidos FROM documentos d JOIN tcp_clientes t ON t.id=d.tcp_id WHERE d.id=?", (doc_id,))
    if not d:
        return redirect(url_for("doc_list"))
    items = json.loads(d["items_json"] or "[]")
    it = "".join(f"<tr><td>{esc(i.get('descripcion',''))}</td><td>{esc(i.get('um',''))}</td><td>{i.get('cantidad','')}</td><td>{fmt_money(i.get('precio',0))}</td><td>{fmt_money(float(i.get('cantidad',0))*float(i.get('precio',0)))}</td></tr>" for i in items)
    cli = db.fetchone("SELECT * FROM clientes_finales WHERE id=?", (d["cliente_final_id"],)) if d["cliente_final_id"] else None
    snap = json.loads(d["snap_json"]) if d.get("snap_json") else None
    cli_txt = esc(cli["empresa"]) if cli else (esc(snap["cliente"].get("empresa","—")) if snap else "—")
    btns = ""
    if d["estado"] == "solicitado":
        btns += f"<a class='btn' href='/documentos/{doc_id}/generar'>⚡ Generar y enviar</a> "
    if d["estado"] in ("generado", "enviado"):
        btns += f"<a class='btn gray' href='/documentos/{doc_id}/pdf'>⬇ Descargar PDF</a> "
    if d["estado"] != "anulado":
        btns += f"<a class='btn red' href='/documentos/{doc_id}/anular' onclick='return confirm(\"¿Anular?\")'>Anular</a>"
    c = f"""<div class="box"><p><b>ID {d['id']}</b> · {esc(d['tipo']).upper()} No. <b>{esc(d['numero'] or '(s/n)')}</b> · <span class='pill p-{esc(d['estado'])}'>{esc(d['estado'])}</span></p>
    <p>TCP: {esc(d['codigo'])} {esc(d['nombre_apellidos'])} · Cliente: {cli_txt} · Contrato: {esc(d['contrato_no'])} · Fecha: {esc(d['fecha'] or ('__/__/____' if d['fecha_blanco'] else '-'))}</p>
    <p style="margin:10px 0">{btns} <a class="btn gray" href="/documentos">Volver</a></p>
    <table><tr><th>Descripción</th><th>U/M</th><th>Cant</th><th>Precio</th><th>Importe</th></tr>{it}</table>
    <p style="text-align:right;margin-top:8px"><b>TOTAL: {fmt_money(sum(float(i.get('cantidad',0))*float(i.get('precio',0)) for i in items))}</b></p></div>"""
    return page(f"Documento {doc_id}", c, "doc", _flash())

@app.route("/documentos/<int:doc_id>/generar")
@admin_required
def doc_generar(doc_id):
    ok, msg = generar_y_enviar(doc_id, session.get("admin", "web"))
    _set_flash("ok" if ok else "err", msg)
    return redirect(url_for("doc_ver", doc_id=doc_id))

@app.route("/documentos/<int:doc_id>/pdf")
@admin_required
def doc_pdf(doc_id):
    d = db.fetchone("SELECT * FROM documentos WHERE id=?", (doc_id,))
    if not d or not d["pdf_blob"]:
        _set_flash("err", "Sin PDF (aún no generado).")
        return redirect(url_for("doc_ver", doc_id=doc_id))
    blob = d["pdf_blob"]
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    pre = "Factura" if d["tipo"] == "factura" else "Oferta"
    return Response(blob, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{pre}_{d["numero"] or doc_id}.pdf"'})

@app.route("/documentos/<int:doc_id>/anular")
@admin_required
def doc_anular(doc_id):
    db.execute("UPDATE documentos SET estado='anulado' WHERE id=?", (doc_id,))
    _set_flash("warn", "Documento anulado.")
    return redirect(url_for("doc_ver", doc_id=doc_id))

# ---------- web: recargas / notif / config ----------
@app.route("/recargas")
@admin_required
def rec_list():
    rows = db.fetchall("SELECT r.*, t.codigo FROM recargas r JOIN tcp_clientes t ON t.id=r.tcp_id ORDER BY r.id DESC LIMIT 100")
    tr = "".join(f"<tr><td>{esc(r['fecha'])}</td><td>{esc(r['codigo'])}</td><td>{esc(r['tipo'])}</td><td>{r['docs']}</td><td>{fmt_money(r['monto'])}</td><td>{esc(r['admin'])}</td><td>{esc(r['nota'])}</td></tr>" for r in rows)
    return page("Recargas", f"<div class='box'><table><tr><th>Fecha</th><th>TCP</th><th>Tipo</th><th>Docs</th><th>Monto</th><th>Admin</th><th>Nota</th></tr>{tr or '<tr><td colspan=7>Ninguna</td></tr>'}</table></div>", "rec")

@app.route("/notificaciones")
@admin_required
def not_list():
    db.execute("UPDATE notificaciones SET leida=1 WHERE destino='admin'")
    rows = db.fetchall("SELECT * FROM notificaciones WHERE destino='admin' ORDER BY id DESC LIMIT 100")
    tr = "".join(f"<tr><td>{esc(n['created_at'])}</td><td><b>{esc(n['titulo'])}</b><br>{esc(n['mensaje'])}</td><td>{esc(n['tipo'])}</td></tr>" for n in rows)
    return page("Notificaciones", f"<div class='box'><table><tr><th>Fecha</th><th>Mensaje</th><th>Tipo</th></tr>{tr or '<tr><td colspan=3>Ninguna</td></tr>'}</table></div>", "not")

@app.route("/config", methods=["GET", "POST"])
@admin_required
def config():
    if request.method == "POST":
        f = request.form
        for k in ("precio_plan", "docs_plan", "dias_plan", "precio_extra", "docs_extra", "dias_gracia", "nombre_sistema"):
            db.set_config(k, f.get(k, ""))
        db.set_config("autogenerar", "1" if f.get("autogenerar") else "0")
        if f.get("newpass"):
            db.execute("UPDATE admin_users SET password_hash=? WHERE username=?",
                       (generate_password_hash(f.get("newpass")), session.get("admin")))
            _set_flash("ok", "Config y clave actualizadas.")
        else:
            _set_flash("ok", "Configuración guardada.")
        return redirect(url_for("config"))
    g = lambda k, d: esc(db.get_config(k, d))
    auto = "checked" if db.get_config("autogenerar", "0") == "1" else ""
    base = request.host_url.rstrip("/")
    c = f"""<div class="box"><form method="post">
    <div class="frow">
    <div><label>Precio plan base (CUP)</label><input name="precio_plan" value="{g('precio_plan','1000')}"></div>
    <div><label>Docs plan base</label><input name="docs_plan" value="{g('docs_plan','100')}"></div>
    <div><label>Días plan base</label><input name="dias_plan" value="{g('dias_plan','30')}"></div></div>
    <div class="frow">
    <div><label>Precio extra (CUP)</label><input name="precio_extra" value="{g('precio_extra','500')}"></div>
    <div><label>Docs extra</label><input name="docs_extra" value="{g('docs_extra','50')}"></div>
    <div><label>Días gracia</label><input name="dias_gracia" value="{g('dias_gracia','15')}"></div></div>
    <div class="frow"><div><label>Nombre sistema</label><input name="nombre_sistema" value="{g('nombre_sistema','Facturador TCP')}"></div>
    <div><label>Nueva clave admin (vacía = no cambiar)</label><input name="newpass" type="password"></div></div>
    <p><label><input type="checkbox" name="autogenerar" style="width:auto" {auto}> <b>Autogenerar</b>: al llegar solicitud de la APK, generar y enviar al instante (consume 1 doc)</label></p>
    <button class="btn">Guardar</button></form></div>
    <div class="box"><h3>API para las APK</h3>
    <p>Base local: <code>{esc(base)}</code> · En Wasmer será su dominio (ej <code>https://mi-facturador.wasmer.app</code>).</p>
    <p>Token admin API (para APK administrativa): <code>{esc(admin_api_token())}</code> <a class="btn sm gray" href="/config/rotar" onclick="return confirm('¿Generar nuevo token? La APK admin deberá actualizarlo.')">Rotar</a></p>
    <pre class="api">Registro:        POST {{base}}/api/registro
Estado (poll):   POST {{base}}/api/estado        (X-Token, X-Device)
Mis clientes:    GET  {{base}}/api/mis-clientes
Solicitar doc:   POST {{base}}/api/solicitar-documento
Mis documentos:  GET  {{base}}/api/mis-documentos
Descargar PDF:   GET  {{base}}/api/documentos/&lt;id&gt;/pdf
Notificaciones:  GET  {{base}}/api/notificaciones
Admin (APK):     POST {{base}}/api/admin/login  +  GET {{base}}/api/admin/* (X-Admin-Token)</pre>
    <p><small>Las APK se identifican con <b>X-Token</b> (único por TCP) + <b>X-Device</b> (ID único del teléfono). Si el dispositivo no coincide, el servidor rechaza: nadie ve datos ajenos.</small></p></div>"""
    return page("Config / API", c, "cfg", _flash())

@app.route("/config/rotar")
@admin_required
def config_rotar():
    db.set_config("admin_api_token", secrets.token_hex(24))
    _set_flash("ok", "Token admin regenerado.")
    return redirect(url_for("config"))

# ---------- API: cliente ----------
def api_auth():
    token = request.headers.get("X-Token", "") or request.args.get("token", "") or (request.get_json(silent=True) or {}).get("token", "")
    device = request.headers.get("X-Device", "") or request.args.get("device", "") or (request.get_json(silent=True) or {}).get("device_id", "")
    device = device or ""
    tcp = get_tcp_by_token(token)
    if not tcp:
        return None, jsonify({"ok": False, "error": "Token inválido. Regístrese de nuevo."}), 401
    # modo ayuda: admin asistiendo a un cliente (no vincula teléfono, no bloquea)
    ah = request.headers.get("X-Admin-Token", "")
    if device.startswith("AYUDA-"):
        if ah and ah == admin_api_token():
            return tcp, None, 0
        return None, jsonify({"ok": False, "error": "Sesión de ayuda: entre al Sim Admin para guardar su clave."}), 403
    # vinculo de dispositivo único (sin robar teléfonos de otra cuenta)
    if not tcp["device_id"]:
        if device:
            other = db.fetchone("SELECT id FROM tcp_clientes WHERE device_id=? AND id!=?", (device, tcp["id"]))
            if other:
                return None, jsonify({"ok": False, "error": "Este teléfono está vinculado a otra cuenta."}), 403
            db.execute("UPDATE tcp_clientes SET device_id=? WHERE id=?", (device, tcp["id"]))
            tcp = get_tcp(tcp["id"])
    elif tcp["device_id"]:
        if not device:
            return None, jsonify({"ok": False, "error": "Falta dispositivo."}), 403
        if tcp["device_id"] != device:
            return None, jsonify({"ok": False, "error": "Dispositivo no autorizado para esta cuenta."}), 403
    return tcp, None, 0

@app.route("/api/registro", methods=["POST"])
def api_registro():
    d = request.get_json(silent=True) or request.form.to_dict()
    nombre = (d.get("nombre_apellidos") or "").strip()
    device = (d.get("device_id") or "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "Falta nombre_apellidos"}), 400
    if not device:
        return jsonify({"ok": False, "error": "Falta device_id (ID único del teléfono)"}), 400
    if db.fetchone("SELECT id FROM tcp_clientes WHERE device_id=?", (device,)):
        return jsonify({"ok": False, "error": "Este teléfono ya tiene una cuenta registrada."}), 400
    token = secrets.token_hex(16)
    codigo = siguiente_codigo_tcp()
    tcp_id = db.execute("""INSERT INTO tcp_clientes (codigo,nombre_apellidos,ci,direccion,telefono,email,cuenta_cup,agencia,codigo_barra,nit,cargo,device_id,device_info,token,estado,docs_disponibles,created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (codigo, nombre, d.get("ci",""), d.get("direccion",""), d.get("telefono",""), d.get("email",""),
       d.get("cuenta_cup",""), d.get("agencia",""), d.get("codigo_barra",""), d.get("nit",""), d.get("cargo","TCP") or "TCP",
       device, d.get("device_info",""), token, "pendiente", 0, db.now_str()))
    notificar("admin", "Nueva solicitud de cuenta", f"{codigo} {nombre} ({d.get('telefono','')}) pide activación.", "registro")
    return jsonify({"ok": True, "token": token, "codigo": codigo, "tcp_id": tcp_id,
                    "estado": "pendiente", "mensaje": "Registro recibido. Espere activación del administrador."})

@app.route("/api/estado", methods=["GET", "POST"])
def api_estado():
    tcp, err, code = api_auth()
    if err:
        return err, code
    tcp = get_tcp(tcp["id"])
    r = {"ok": True, "codigo": tcp["codigo"], "estado": tcp["estado"], "docs": tcp["docs_disponibles"] or 0,
         "plan_fin": tcp["plan_fin"] or "", "activo": False, "en_gracia": False, "mensaje": ""}
    if tcp["estado"] == "pendiente":
        r["mensaje"] = "En espera de activación por el administrador."
        return jsonify(r)
    vig = estado_vigencia(tcp)
    tcp = get_tcp(tcp["id"])
    r.update({"estado": tcp["estado"], "docs": tcp["docs_disponibles"] or 0, "plan_fin": tcp["plan_fin"] or "",
              "activo": vig["ok"], "en_gracia": vig.get("gracia", False), "mensaje": vig["mensaje"] if not vig["ok"] or vig.get("gracia") else "Cuenta activa."})
    if vig["ok"] and (tcp["docs_disponibles"] or 0) <= 0:
        r["activo"] = False
        r["mensaje"] = "Sin documentos. Solicite una recarga."
    return jsonify(r)

@app.route("/api/mis-clientes", methods=["GET"])
def api_mis_clientes():
    tcp, err, code = api_auth()
    if err:
        return err, code
    rows = db.fetchall("SELECT id, empresa, cuenta_cup, cuenta_cuc, agencia, codigo, nit, telefono_whatsapp, direccion FROM clientes_finales WHERE tcp_id=? ORDER BY empresa", (tcp["id"],))
    return jsonify({"ok": True, "clientes": rows})

@app.route("/api/solicitar-documento", methods=["POST"])
def api_solicitar():
    tcp, err, code = api_auth()
    if err:
        return err, code
    tcp = get_tcp(tcp["id"])
    vig = estado_vigencia(tcp)
    if not vig["ok"]:
        return jsonify({"ok": False, "error": vig["mensaje"], "requiere_recarga": True}), 402
    if (tcp["docs_disponibles"] or 0) <= 0:
        return jsonify({"ok": False, "error": "Consumió sus documentos. Solicite recarga (extra 50 docs).", "requiere_recarga": True}), 402
    d = request.get_json(silent=True) or {}
    tipo = d.get("tipo", "factura")
    if tipo not in ("factura", "oferta"):
        return jsonify({"ok": False, "error": "tipo debe ser factura u oferta"}), 400
    cli_id = int(d.get("cliente_final_id", 0) or 0)
    if cli_id and not db.fetchone("SELECT id FROM clientes_finales WHERE id=? AND tcp_id=?", (cli_id, tcp["id"])):
        return jsonify({"ok": False, "error": "Cliente final inválido"}), 400
    items = d.get("items", [])
    if not items:
        return jsonify({"ok": False, "error": "Sin artículos"}), 400
    norm = []
    for i in items[:15]:
        try:
            norm.append({"descripcion": str(i.get("descripcion",""))[:200], "um": str(i.get("um","U"))[:8],
                         "cantidad": float(i.get("cantidad",0)), "precio": float(i.get("precio",0))})
        except (ValueError, TypeError):
            pass
    if not norm:
        return jsonify({"ok": False, "error": "Artículos inválidos"}), 400
    fecha = d.get("fecha")
    if fecha is None:
        fecha = hoy_iso()
    f_blanco = 1 if (d.get("fecha_blanco") or not fecha) else 0
    doc_id = db.execute("INSERT INTO documentos (numero,tipo,tcp_id,cliente_final_id,contrato_no,fecha,numero_blanco,fecha_blanco,items_json,total,estado,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("", tipo, tcp["id"], cli_id, d.get("contrato_no",""), fecha,
                         1 if d.get("numero_blanco") else 0, f_blanco,
                         json.dumps(norm, ensure_ascii=False), 0, "solicitado", db.now_str()))
    notificar("admin", "Nueva solicitud de documento",
              f"{tcp['codigo']}: {tipo} (id {doc_id}) de {len(norm)} artículos. {'En gracia' if vig.get('gracia') else ''}", "solicitud",
              extra=json.dumps({"doc_id": doc_id}))
    if db.get_config("autogenerar", "0") == "1":
        ok, msg = generar_y_enviar(doc_id, "auto")
        tcp = get_tcp(tcp["id"])
        return jsonify({"ok": ok, "doc_id": doc_id, "estado": "enviado" if ok else "solicitado",
                        "mensaje": msg, "docs_restantes": tcp["docs_disponibles"] or 0})
    return jsonify({"ok": True, "doc_id": doc_id, "estado": "solicitado",
                    "mensaje": "Solicitud enviada. Le avisaremos cuando el documento esté listo."})

@app.route("/api/mis-documentos", methods=["GET"])
def api_mis_docs():
    tcp, err, code = api_auth()
    if err:
        return err, code
    rows = db.fetchall("""SELECT d.id, d.numero, d.tipo, d.estado, d.total, d.fecha, d.created_at, d.generated_at,
      COALESCE(c.empresa,'') empresa FROM documentos d LEFT JOIN clientes_finales c ON c.id=d.cliente_final_id
      WHERE d.tcp_id=? ORDER BY d.id DESC LIMIT 100""", (tcp["id"],))
    for r in rows:
        r["pdf"] = r["estado"] in ("generado", "enviado")
        r["total_txt"] = fmt_money(r["total"])
    return jsonify({"ok": True, "documentos": rows})

@app.route("/api/documentos/<int:doc_id>/pdf", methods=["GET"])
def api_doc_pdf(doc_id):
    tcp, err, code = api_auth()
    if err:
        return err, code
    d = db.fetchone("SELECT * FROM documentos WHERE id=? AND tcp_id=?", (doc_id, tcp["id"]))
    if not d or not d["pdf_blob"]:
        return jsonify({"ok": False, "error": "PDF no disponible aún."}), 404
    blob = d["pdf_blob"]
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    pre = "Factura" if d["tipo"] == "factura" else "Oferta"
    return Response(blob, mimetype="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{pre}_{d["numero"] or doc_id}.pdf"'})

@app.route("/api/notificaciones", methods=["GET"])
def api_notif():
    tcp, err, code = api_auth()
    if err:
        return err, code
    rows = db.fetchall("SELECT id, titulo, mensaje, tipo, leida, created_at, extra FROM notificaciones WHERE destino=? ORDER BY id DESC LIMIT 50", (f"tcp:{tcp['id']}",))
    return jsonify({"ok": True, "notificaciones": rows})

@app.route("/api/notificaciones/leer", methods=["POST"])
def api_notif_leer():
    tcp, err, code = api_auth()
    if err:
        return err, code
    db.execute("UPDATE notificaciones SET leida=1 WHERE destino=?", (f"tcp:{tcp['id']}",))
    return jsonify({"ok": True})

@app.route("/api/cron", methods=["GET"])
def api_cron():
    n = revisar_vencimientos()
    return jsonify({"ok": True, "bajas": n})

# ---------- API: admin (para APK administrativa, Parte 3) ----------
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    d = request.get_json(silent=True) or {}
    r = db.fetchone("SELECT * FROM admin_users WHERE username=?", (d.get("username",""),))
    if r and check_password_hash(r["password_hash"], d.get("password","")):
        return jsonify({"ok": True, "token": admin_api_token()})
    return jsonify({"ok": False, "error": "Credenciales inválidas"}), 401

@app.route("/api/admin/resumen", methods=["GET"])
def api_admin_resumen():
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    revisar_vencimientos()
    return jsonify({"ok": True, "resumen": {
        "tcp_total": db.fetchone("SELECT COUNT(*) c FROM tcp_clientes")["c"],
        "tcp_activos": db.fetchone("SELECT COUNT(*) c FROM tcp_clientes WHERE estado='activo'")["c"],
        "tcp_pendientes": db.fetchone("SELECT COUNT(*) c FROM tcp_clientes WHERE estado='pendiente'")["c"],
        "solicitudes": db.fetchone("SELECT COUNT(*) c FROM documentos WHERE estado='solicitado'")["c"],
        "enviados": db.fetchone("SELECT COUNT(*) c FROM documentos WHERE estado='enviado'")["c"],
        "cobrado": db.fetchone("SELECT COALESCE(SUM(monto),0) s FROM recargas")["s"],
        "notif_no_leidas": db.fetchone("SELECT COUNT(*) c FROM notificaciones WHERE destino='admin' AND leida=0")["c"],
    }})

@app.route("/api/admin/tcp", methods=["GET"])
def api_admin_tcp():
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    rows = db.fetchall("SELECT id,codigo,nombre_apellidos,telefono,estado,docs_disponibles,plan_fin,device_id FROM tcp_clientes ORDER BY id DESC", ())
    return jsonify({"ok": True, "tcp": rows})

@app.route("/api/admin/activar/<int:tcp_id>", methods=["POST"])
def api_admin_activar(tcp_id):
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    d = request.get_json(silent=True) or {}
    if d.get("modo") == "extra":
        ok, msg = recarga_extra(tcp_id, "apk-admin")
        return jsonify({"ok": ok, "mensaje": msg})
    docs, fin = activar_plan(tcp_id, "apk-admin")
    return jsonify({"ok": True, "mensaje": f"Activado: {docs} docs hasta {fin.strftime('%d/%m/%Y')}"})

@app.route("/api/admin/solicitudes", methods=["GET"])
def api_admin_sol():
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    rows = db.fetchall("""SELECT d.id,d.numero,d.tipo,d.estado,d.contrato_no,d.fecha,d.items_json,d.created_at,t.codigo,t.nombre_apellidos,
      COALESCE(c.empresa,'') empresa FROM documentos d JOIN tcp_clientes t ON t.id=d.tcp_id
      LEFT JOIN clientes_finales c ON c.id=d.cliente_final_id WHERE d.estado='solicitado' ORDER BY d.id DESC""", ())
    for r in rows:
        r["items"] = json.loads(r.pop("items_json") or "[]")
    return jsonify({"ok": True, "solicitudes": rows})

@app.route("/api/admin/generar/<int:doc_id>", methods=["POST"])
def api_admin_generar(doc_id):
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    ok, msg = generar_y_enviar(doc_id, "apk-admin")
    return jsonify({"ok": ok, "mensaje": msg})

@app.route("/api/admin/notificaciones", methods=["GET"])
def api_admin_notif():
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    rows = db.fetchall("SELECT id,titulo,mensaje,tipo,leida,created_at,extra FROM notificaciones WHERE destino='admin' ORDER BY id DESC LIMIT 50", ())
    db.execute("UPDATE notificaciones SET leida=1 WHERE destino='admin'")
    return jsonify({"ok": True, "notificaciones": rows})

@app.route("/api/admin/documentos/<int:doc_id>/pdf", methods=["GET"])
def api_admin_pdf(doc_id):
    tok = request.headers.get("X-Admin-Token", "") or request.args.get("token", "")
    if tok != admin_api_token():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    d = db.fetchone("SELECT * FROM documentos WHERE id=?", (doc_id,))
    if not d or not d["pdf_blob"]:
        return jsonify({"ok": False, "error": "Sin PDF"}), 404
    blob = d["pdf_blob"]
    if isinstance(blob, memoryview):
        blob = blob.tobytes()
    return Response(blob, mimetype="application/pdf")

# ---------- simulador APK cliente (prueba local) ----------
# ---------- simulador APK cliente (prueba local) ----------
# ---------- simulador APK cliente (prueba local) ----------
@app.route("/simulador")
@admin_required
def simulador():
    cuentas = db.fetchall("SELECT codigo, nombre_apellidos, device_id, token FROM tcp_clientes ORDER BY id")
    cuentas_json = json.dumps([{"codigo": c["codigo"], "nombre": c["nombre_apellidos"], "dev": c["device_id"] or "", "tok": c["token"]} for c in cuentas], ensure_ascii=False)
    c = """<div id="perfil_bar" class="box" style="display:none;background:#ecfdf5;border:1px solid #6ee7b7"></div>
    <div class="box" id="box_sesion"><p>Esto <b>simula la APK del cliente</b> usando la API real. Si el teléfono ya está registrado, <b>se carga solo</b> al abrir.</p>
    <div><label>📱 Teléfono registrado (elegir para cargar)</label><select id="sel_tel" onchange="elegirTel()"><option value="">— Elegir —</option></select></div>
    <div class="frow"><div><label>Device ID (único del teléfono)</label><input id="dev" value="TEST-PHONE-001"></div>
    <div><label>Token (se recupera y guarda solo)</label><input id="tok" placeholder="vacío = sin registrar" readonly onclick="this.select()"></div></div>
    <p><button class="btn sm" onclick="poll()">🔄 Estado ahora</button>
    <button class="btn sm gray" onclick="cargarTodo()">📥 Cargar todo</button>
    <label style="font-weight:normal"><input type="checkbox" id="auto" style="width:auto" checked> auto-cada 4s</label>
    <span id="est" class="pill p-pendiente">—</span></p>
    <div id="res" style="background:#ecfdf5;border:1px solid #6ee7b7;border-radius:10px;padding:10px;margin-bottom:8px;display:none"></div>
    <div id="log" style="background:#0f172a;color:#a5f3fc;padding:10px;border-radius:10px;font-size:12.5px;max-height:150px;overflow:auto"></div></div>
    <div class="box" id="box_reg"><h3>📝 Registro (pide todos los datos + TCP)</h3>
    <div class="frow"><div><label>Nombre*</label><input id="r_nom"></div><div><label>CI</label><input id="r_ci"></div></div>
    <div class="frow"><div><label>Teléfono</label><input id="r_tel"></div><div><label>Dirección</label><input id="r_dir"></div></div>
    <div class="frow"><div><label>Cuenta CUP</label><input id="r_cup"></div><div><label>NIT</label><input id="r_nit"></div></div>
    <button class="btn" onclick="registro()">Solicitar registro</button></div>
    <div id="box_main" style="display:none">
    <div class="box"><h3>📄 Solicitar documento</h3>
    <div class="frow"><div><label>Tipo</label><select id="s_tipo"><option value="factura">FACTURA</option><option value="oferta">OFERTA</option></select></div>
    <div><label>Cliente final (cargados del servidor)</label><select id="s_cli"></select></div><div><label>Contrato</label><input id="s_cont"></div></div>
    <div id="items"></div><button class="btn gray sm" onclick="addItem()">+ artículo</button>
    <button class="btn" onclick="solicitar()">Enviar solicitud</button></div>
    <div class="box"><h3>📁 Mis documentos / PDF / WhatsApp</h3><div id="docs" style="margin-top:6px"></div></div>
    <div class="box"><h3>🔔 Notificaciones</h3><div id="avis"></div></div>
    </div>
    <div class="box"><h3>⚙️ Configuración del cliente</h3>
    <p><button class="btn sm gray" onclick="toggleSesion()">📱 Mostrar / ocultar sesión</button>
    <button class="btn sm gray" onclick="toggleReg()">📝 Mostrar / ocultar registro</button>
    <button class="btn sm red" onclick="borrarSesion()">🗑 Borrar datos locales</button></p>
    <p><small>Sesión y registro se ocultan solos cuando hay cuenta. Solo aparecen si los pide aquí.</small></p></div>
    <script>""" + "var CUENTAS=" + cuentas_json + ";" + """
    var BASE='';
    function log(t){var l=document.getElementById('log');l.innerHTML=new Date().toLocaleTimeString()+' '+t+'<br>'+l.innerHTML;}
    function hd(){return {'Content-Type':'application/json','X-Token':document.getElementById('tok').value,'X-Device':(document.getElementById('dev').value||'AYUDA-ADMIN'),'X-Admin-Token':(localStorage.getItem('fw_atok')||'')};}
    function save(){try{localStorage.setItem('fw_dev',document.getElementById('dev').value);localStorage.setItem('fw_tok',document.getElementById('tok').value);}catch(e){}}
    function toggleReg(){var b=document.getElementById('box_reg');b.style.display=(b.style.display==='none')?'':'none';if(b.style.display===''){window._manSes=true;}}
    function toggleSesion(){var b=document.getElementById('box_sesion');b.style.display=(b.style.display==='none')?'':'none';if(b.style.display===''){window._manSes=true;}}
    function borrarSesion(){try{localStorage.removeItem('fw_dev');localStorage.removeItem('fw_tok');}catch(e){}location.reload();}
    function showMain(on){document.getElementById('box_main').style.display=on?'':'none';if(on){document.getElementById('box_reg').style.display='none';}}
    function autoTok(){var td=document.getElementById('tok');if(td.value){return true;}var dv=document.getElementById('dev').value;for(var i=0;i<CUENTAS.length;i++){if(CUENTAS[i].dev&&CUENTAS[i].dev===dv){td.value=CUENTAS[i].tok;save();log('auto: token recuperado para '+dv);return true;}}return false;}
    function elegirTel(){window._manSes=false;var sel=document.getElementById('sel_tel');var o=sel.selectedOptions[0];if(!o||!o.dataset.tok){return;}document.getElementById('dev').value=o.value;document.getElementById('tok').value=o.dataset.tok;save();window._loaded=false;poll();}
    function registro(){fetch(BASE+'/api/registro',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({nombre_apellidos:document.getElementById('r_nom').value,ci:document.getElementById('r_ci').value,telefono:document.getElementById('r_tel').value,direccion:document.getElementById('r_dir').value,cuenta_cup:document.getElementById('r_cup').value,nit:document.getElementById('r_nit').value,device_id:document.getElementById('dev').value,device_info:navigator.userAgent})}).then(r=>r.json()).then(j=>{log(JSON.stringify(j));if(j.ok){document.getElementById('tok').value=j.token;save();poll();}});}
    function vistaPerfil(j){var dev=document.getElementById('dev').value;var as=dev?'':'🛟 AYUDA ADMIN · ';var nom='';CUENTAS.forEach(function(a){if((a.dev||'')===dev){nom=a.nombre;}});var b=document.getElementById('perfil_bar');b.style.display='';b.innerHTML=as+'<b>📱 '+(j.codigo||'')+'</b> '+nom+' · '+dev+'<br>Estado: <b>'+j.estado+'</b> · Docs: <b>'+j.docs+'</b> · Vence: '+(j.plan_fin||'-')+' · '+(j.mensaje||'')+' <button class="btn sm gray" onclick="poll()">🔄</button> <button class="btn sm gray" onclick="toggleSesion()">⚙️ Sesión</button>';if(!window._manSes){document.getElementById('box_sesion').style.display='none';document.getElementById('box_reg').style.display='none';}showMain(true);}
    function poll(){autoTok();var t=document.getElementById('tok').value;if(!t){log('sin token: elija telefono o registre');return;}fetch(BASE+'/api/estado',{method:'POST',headers:hd()}).then(function(r){if(r.status===401||r.status===403){return r.json().then(function(j){throw j;});}return r.json();}).then(function(j){log('estado: '+JSON.stringify(j));var e=document.getElementById('est');e.textContent=j.estado+' · docs:'+j.docs;e.className='pill '+(j.activo?'p-activo':'p-pendiente');var r=document.getElementById('res');r.style.display='';r.innerHTML='<b>'+(j.codigo||'')+'</b> · Estado: <b>'+j.estado+'</b> · Docs: <b>'+j.docs+'</b> · Vence: '+(j.plan_fin||'-')+'<br>'+(j.mensaje||'');vistaPerfil(j);if(!window._loaded){window._loaded=true;cargarTodo();}}).catch(function(j){log('sesion invalida, revise telefono/token: '+JSON.stringify(j));document.getElementById('box_sesion').style.display='';document.getElementById('perfil_bar').style.display='none';showMain(false);});}
    setInterval(function(){if(document.getElementById('auto').checked){poll();}},4000);
    function cargarTodo(){cargarCli();cargarDocs();cargarNotif();}
    function cargarCli(){fetch(BASE+'/api/mis-clientes',{headers:hd()}).then(r=>r.json()).then(j=>{log('clientes: '+(j.clientes||[]).length);var s=document.getElementById('s_cli');s.innerHTML='';if(!(j.clientes||[]).length){s.innerHTML='<option value=0>— Sin clientes (el admin los crea) —</option>';return;}(j.clientes||[]).forEach(function(c){var o=document.createElement('option');o.value=c.id;o.textContent=c.empresa+' ('+(c.telefono_whatsapp||'sin WA')+')';o.dataset.wa=c.telefono_whatsapp||'';s.appendChild(o);});});}
    var N=0;function addItem(){var d=document.createElement('div');d.className='itemrow';d.innerHTML='<div><input placeholder=Descripción id=d'+N+'></div><div><input value=U id=u'+N+'></div><div><input type=number placeholder=Cant id=c'+N+'></div><div><input type=number placeholder=Precio id=p'+N+'></div><div></div>';document.getElementById('items').appendChild(d);N++;}
    addItem();addItem();
    function solicitar(){var items=[];for(var i=0;i<N;i++){var dd=document.getElementById('d'+i);if(dd&&dd.value){items.push({descripcion:dd.value,um:document.getElementById('u'+i).value,cantidad:parseFloat(document.getElementById('c'+i).value||0),precio:parseFloat(document.getElementById('p'+i).value||0)});}}
    fetch(BASE+'/api/solicitar-documento',{method:'POST',headers:hd(),body:JSON.stringify({tipo:document.getElementById('s_tipo').value,cliente_final_id:document.getElementById('s_cli').value||0,contrato_no:document.getElementById('s_cont').value,items:items})}).then(r=>r.json()).then(j=>{log(JSON.stringify(j));alert(j.mensaje||j.error||'OK');cargarDocs();cargarNotif();});}
    function cargarDocs(){fetch(BASE+'/api/mis-documentos',{headers:hd()}).then(r=>r.json()).then(j=>{log('docs: '+(j.documentos||[]).length);var h='<table><tr><th>ID</th><th>Tipo</th><th>No.</th><th>Estado</th><th>Total</th><th></th></tr>';(j.documentos||[]).forEach(function(d){h+='<tr><td>'+d.id+'</td><td>'+d.tipo+'</td><td>'+(d.numero||'(s/n)')+'</td><td>'+d.estado+'</td><td>'+d.total_txt+'</td><td>';if(d.pdf){h+='<a class="btn sm gray" href="'+BASE+'/api/documentos/'+d.id+'/pdf?token='+document.getElementById('tok').value+'&device='+document.getElementById('dev').value+'">PDF</a> ';var sel=document.getElementById('s_cli');var wa=sel&&sel.selectedOptions.length?sel.selectedOptions[0].dataset.wa:'';var url=wa?('https://wa.me/'+wa+'?text='+encodeURIComponent('Le envío su documento '+(d.numero||d.id))):'https://wa.me/?text='+encodeURIComponent('Documento '+(d.numero||d.id));h+='<a class="btn sm" target="_blank" href="'+url+'">WhatsApp</a>';}h+='</td></tr>';});h+='</table>';document.getElementById('docs').innerHTML=h;});}
    function cargarNotif(){fetch(BASE+'/api/notificaciones',{headers:hd()}).then(r=>r.json()).then(j=>{var h='<table>';(j.notificaciones||[]).forEach(function(n){h+='<tr><td><b>'+n.titulo+'</b><br>'+n.mensaje+'<br><small>'+n.created_at+'</small></td><td>'+(n.leida?'✓':'<b>●</b>')+'</td></tr>';});h+='</table>';document.getElementById('avis').innerHTML=h;fetch(BASE+'/api/notificaciones/leer',{method:'POST',headers:hd()});});}
    (function init(){try{var q=new URLSearchParams(location.search);var qd=q.has('dev')?q.get('dev'):null;var qt=q.get('tok');var sel=document.getElementById('sel_tel');CUENTAS.forEach(function(a){var o=document.createElement('option');o.value=a.dev||'';o.textContent=(a.dev?('📱 '+a.dev+' — '):'🛟 AYUDA — ')+a.codigo+' '+a.nombre;o.dataset.tok=a.tok;sel.appendChild(o);});var d=(qd!==null&&qd!==undefined)?qd:(localStorage.getItem('fw_dev')||document.getElementById('dev').value);var t=qt||localStorage.getItem('fw_tok')||'';if(!t){var cd=CUENTAS.filter(function(a){return a.dev;});if(d){var m=cd.filter(function(a){return a.dev===d;});if(m.length){t=m[0].tok;log('auto: token recuperado para '+d);}}if(!t&&cd.length===1){d=cd[0].dev;t=cd[0].tok;log('auto: unico telefono, cargado solo');}}document.getElementById('dev').value=d||'';if(d){try{sel.value=d;}catch(e){}}if(t){document.getElementById('tok').value=t;}save();if(t){poll();}else{log('sin sesion: elija telefono o registre');}}catch(e){}})();
    </script>"""
    return page("Simulador APK cliente", c, "sim")

# ---------- API admin extra (paridad total con la web) ----------
def _req_admin():
    if not check_admin_api():
        return jsonify({"ok": False, "error": "No autorizado"}), 401
    return None

@app.route("/api/admin/tcp/<int:tcp_id>", methods=["GET"])
def api_admin_tcp_det(tcp_id):
    r = _req_admin()
    if r:
        return r
    t = get_tcp(tcp_id)
    if not t:
        return jsonify({"ok": False, "error": "No existe"}), 404
    t = dict(t)
    t.pop("cuno_blob", None)
    t.pop("firma_blob", None)
    return jsonify({"ok": True, "tcp": t})

@app.route("/api/admin/tcp", methods=["POST"])
def api_admin_tcp_crear():
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    nombre = (d.get("nombre_apellidos") or "").strip()
    if not nombre:
        return jsonify({"ok": False, "error": "Falta nombre_apellidos"}), 400
    tcp_id = db.execute("""INSERT INTO tcp_clientes (codigo,nombre_apellidos,ci,direccion,telefono,email,cuenta_cup,agencia,codigo_barra,nit,cargo,token,estado,docs_disponibles,created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (siguiente_codigo_tcp(), nombre, d.get("ci", ""), d.get("direccion", ""), d.get("telefono", ""), d.get("email", ""),
       d.get("cuenta_cup", ""), d.get("agencia", ""), d.get("codigo_barra", ""), d.get("nit", ""),
       d.get("cargo", "TCP") or "TCP", secrets.token_hex(16), "pendiente", 0, db.now_str()))
    notificar("admin", "TCP creado", f"{nombre} registrado desde APK admin, pendiente de activar.", "info")
    return jsonify({"ok": True, "tcp_id": tcp_id})

@app.route("/api/admin/tcp/<int:tcp_id>", methods=["PUT"])
def api_admin_tcp_editar(tcp_id):
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    campos = ("nombre_apellidos", "ci", "direccion", "telefono", "email", "cuenta_cup", "agencia", "codigo_barra", "nit", "cargo")
    sets, vals = [], []
    for k in campos:
        if k in d:
            sets.append(f"{k}=?")
            vals.append(d[k])
    if not sets:
        return jsonify({"ok": False, "error": "Nada que actualizar"}), 400
    vals.append(tcp_id)
    db.execute(f"UPDATE tcp_clientes SET {','.join(sets)} WHERE id=?", tuple(vals))
    return jsonify({"ok": True})

@app.route("/api/admin/tcp/<int:tcp_id>/suspender", methods=["POST"])
def api_admin_tcp_susp(tcp_id):
    r = _req_admin()
    if r:
        return r
    t = get_tcp(tcp_id)
    if not t:
        return jsonify({"ok": False, "error": "No existe"}), 404
    db.execute("UPDATE tcp_clientes SET estado='suspendido' WHERE id=?", (tcp_id,))
    notificar(f"tcp:{tcp_id}", "Cuenta suspendida", "Su cuenta fue suspendida por el administrador.", "baja")
    return jsonify({"ok": True, "mensaje": "Suspendido."})

@app.route("/api/admin/tcp/<int:tcp_id>/imagen", methods=["POST"])
def api_admin_tcp_img(tcp_id):
    r = _req_admin()
    if r:
        return r
    if not get_tcp(tcp_id):
        return jsonify({"ok": False, "error": "No existe"}), 404
    cuno = request.files.get("cuno")
    firma = request.files.get("firma")
    if cuno and cuno.filename:
        data = cuno.read(5 * 1024 * 1024)
        db.execute("UPDATE tcp_clientes SET cuno_blob=?, cuno_filename=? WHERE id=?", (data, cuno.filename, tcp_id))
    if firma and firma.filename:
        data = firma.read(5 * 1024 * 1024)
        db.execute("UPDATE tcp_clientes SET firma_blob=?, firma_filename=? WHERE id=?", (data, firma.filename, tcp_id))
    d = request.get_json(silent=True) or {}
    import base64
    for campo, blobc, nomc in (("cuno_b64", "cuno_blob", "cuno_filename"), ("firma_b64", "firma_blob", "firma_filename")):
        if d.get(campo):
            try:
                raw = base64.b64decode(d[campo][:7 * 1024 * 1024])
            except Exception:
                return jsonify({"ok": False, "error": f"{campo} inválido"}), 400
            db.execute(f"UPDATE tcp_clientes SET {blobc}=?, {nomc}=? WHERE id=?", (raw, d.get(campo + "_nombre", "apk.png"), tcp_id))
    return jsonify({"ok": True, "mensaje": "Imágenes guardadas."})

@app.route("/api/admin/clientes", methods=["GET"])
def api_admin_cli():
    r = _req_admin()
    if r:
        return r
    tcp_f = request.args.get("tcp", "")
    q = "SELECT c.*, t.codigo FROM clientes_finales c JOIN tcp_clientes t ON t.id=c.tcp_id"
    p = ()
    if tcp_f:
        q += " WHERE c.tcp_id=?"
        p = (tcp_f,)
    q += " ORDER BY c.empresa"
    return jsonify({"ok": True, "clientes": db.fetchall(q, p)})

@app.route("/api/admin/clientes", methods=["POST"])
def api_admin_cli_crear():
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    if not d.get("tcp_id") or not (d.get("empresa") or "").strip():
        return jsonify({"ok": False, "error": "Faltan tcp_id / empresa"}), 400
    cid = db.execute("INSERT INTO clientes_finales (tcp_id,empresa,cuenta_cup,cuenta_cuc,agencia,codigo,nit,telefono_whatsapp,direccion,notas,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (d.get("tcp_id"), d.get("empresa", "").strip(), d.get("cuenta_cup", ""), d.get("cuenta_cuc", ""), d.get("agencia", ""),
                      d.get("codigo", ""), d.get("nit", ""), d.get("telefono_whatsapp", ""), d.get("direccion", ""), d.get("notas", ""), db.now_str()))
    return jsonify({"ok": True, "cliente_id": cid})

@app.route("/api/admin/clientes/<int:cid>", methods=["PUT"])
def api_admin_cli_editar(cid):
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    campos = ("empresa", "cuenta_cup", "cuenta_cuc", "agencia", "codigo", "nit", "telefono_whatsapp", "direccion", "notas")
    sets, vals = [], []
    for k in campos:
        if k in d:
            sets.append(f"{k}=?")
            vals.append(d[k])
    if not sets:
        return jsonify({"ok": False, "error": "Nada que actualizar"}), 400
    vals.append(cid)
    db.execute(f"UPDATE clientes_finales SET {','.join(sets)} WHERE id=?", tuple(vals))
    return jsonify({"ok": True})

@app.route("/api/admin/clientes/<int:cid>", methods=["DELETE"])
def api_admin_cli_del(cid):
    r = _req_admin()
    if r:
        return r
    db.execute("DELETE FROM clientes_finales WHERE id=?", (cid,))
    return jsonify({"ok": True})

@app.route("/api/admin/documentos", methods=["GET"])
def api_admin_docs():
    r = _req_admin()
    if r:
        return r
    q = """SELECT d.id,d.numero,d.tipo,d.estado,d.total,d.fecha,d.contrato_no,d.created_at,t.codigo,
      COALESCE(c.empresa,'') empresa FROM documentos d JOIN tcp_clientes t ON t.id=d.tcp_id
      LEFT JOIN clientes_finales c ON c.id=d.cliente_final_id WHERE 1=1"""
    p = []
    if request.args.get("estado"):
        q += " AND d.estado=?"
        p.append(request.args.get("estado"))
    if request.args.get("tcp"):
        q += " AND d.tcp_id=?"
        p.append(request.args.get("tcp"))
    q += " ORDER BY d.id DESC LIMIT 100"
    rows = db.fetchall(q, tuple(p))
    for x in rows:
        x["total_txt"] = fmt_money(x["total"])
        x["pdf"] = x["estado"] in ("generado", "enviado")
    return jsonify({"ok": True, "documentos": rows})

@app.route("/api/admin/documentos", methods=["POST"])
def api_admin_docs_crear():
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    try:
        tcp_id = int(d.get("tcp_id", 0))
    except (ValueError, TypeError):
        tcp_id = 0
    if not tcp_id or not get_tcp(tcp_id):
        return jsonify({"ok": False, "error": "tcp_id inválido"}), 400
    items = []
    for i in (d.get("items") or [])[:15]:
        try:
            if str(i.get("descripcion", "")).strip():
                items.append({"descripcion": str(i.get("descripcion", ""))[:200], "um": str(i.get("um", "U"))[:8],
                              "cantidad": float(i.get("cantidad", 0)), "precio": float(i.get("precio", 0))})
        except (ValueError, TypeError):
            pass
    if not items:
        return jsonify({"ok": False, "error": "Sin artículos"}), 400
    fecha = d.get("fecha") or ""
    doc_id = db.execute("INSERT INTO documentos (numero,tipo,tcp_id,cliente_final_id,contrato_no,fecha,numero_blanco,fecha_blanco,items_json,total,estado,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        ("", d.get("tipo", "factura"), tcp_id, int(d.get("cliente_final_id", 0) or 0), d.get("contrato_no", ""), fecha,
                         1 if d.get("numero_blanco") else 0, 1 if (d.get("fecha_blanco") or not fecha) else 0,
                         json.dumps(items, ensure_ascii=False), 0, "solicitado", db.now_str()))
    ok, msg = generar_y_enviar(doc_id, "apk-admin")
    return jsonify({"ok": ok, "doc_id": doc_id, "mensaje": msg})

@app.route("/api/admin/documentos/<int:doc_id>/anular", methods=["POST"])
def api_admin_docs_anular(doc_id):
    r = _req_admin()
    if r:
        return r
    db.execute("UPDATE documentos SET estado='anulado' WHERE id=?", (doc_id,))
    return jsonify({"ok": True})

@app.route("/api/admin/recargas", methods=["GET"])
def api_admin_rec():
    r = _req_admin()
    if r:
        return r
    rows = db.fetchall("SELECT r.*, t.codigo FROM recargas r JOIN tcp_clientes t ON t.id=r.tcp_id ORDER BY r.id DESC LIMIT 100", ())
    for x in rows:
        x["monto_txt"] = fmt_money(x["monto"])
    return jsonify({"ok": True, "recargas": rows})

@app.route("/api/admin/config", methods=["GET"])
def api_admin_cfg_get():
    r = _req_admin()
    if r:
        return r
    return jsonify({"ok": True, "config": {k: db.get_config(k, "") for k in
        ("precio_plan", "docs_plan", "dias_plan", "precio_extra", "docs_extra", "dias_gracia", "autogenerar", "nombre_sistema")}})

@app.route("/api/admin/config", methods=["PUT"])
def api_admin_cfg_put():
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    for k in ("precio_plan", "docs_plan", "dias_plan", "precio_extra", "docs_extra", "dias_gracia", "autogenerar", "nombre_sistema"):
        if k in d:
            db.set_config(k, str(d[k]))
    return jsonify({"ok": True})

@app.route("/api/admin/password", methods=["POST"])
def api_admin_pass():
    r = _req_admin()
    if r:
        return r
    d = request.get_json(silent=True) or {}
    u = db.fetchone("SELECT * FROM admin_users WHERE username=?", (d.get("username", "admin"),))
    if not u or not check_password_hash(u["password_hash"], d.get("old", "")):
        return jsonify({"ok": False, "error": "Clave actual incorrecta"}), 400
    if len(d.get("new", "")) < 4:
        return jsonify({"ok": False, "error": "Nueva clave muy corta"}), 400
    db.execute("UPDATE admin_users SET password_hash=? WHERE id=?", (generate_password_hash(d["new"]), u["id"]))
    return jsonify({"ok": True, "mensaje": "Clave actualizada."})

# ---------- simulador APP ADMINISTRACION (prueba local, API admin) ----------
@app.route("/simulador-admin")
@admin_required
def simulador_admin():
    c = """<style>
    .phone{max-width:560px;margin:0 auto}
    .tabs{display:flex;gap:6px;margin:8px 0;flex-wrap:wrap}
    .tabs button{flex:1;min-width:80px;padding:10px 4px;border:none;border-radius:11px;background:#e2e8f0;font-weight:700;cursor:pointer;font-size:13px}
    .tabs button.on{background:#0d9488;color:#fff}
    .doc{background:#f8fafc;border:1px solid #e2e8f0;border-radius:11px;padding:10px;margin-bottom:10px}
    .cnt{background:#ef4444;color:#fff;border-radius:12px;padding:0 8px;font-size:12px}
    details{margin:8px 0;border:1px dashed #94a3b8;border-radius:10px;padding:8px}
    summary{font-weight:700;cursor:pointer}
    </style>
    <div class="phone">
    <div class="box" id="alog"><h3>🛡️ App Admin — entrar</h3>
    <label>Usuario</label><input id="a_user" value="admin">
    <label>Clave</label><input id="a_pass" type="password" value="admin123">
    <button class="btn" onclick="alogin()">Entrar</button>
    <p><small>Todo funciona por <code>/api/admin/*</code> igual que la futura APK. Mismas opciones que la web.</small></p></div>
    <div id="aapp" style="display:none">
    <div class="box"><b>🛡️ Admin</b> <span id="ares"></span>
    <div class="tabs">
      <button id="t1" class="on" onclick="tab('sol')">📥 Solic. <span class="cnt" id="c_sol">0</span></button>
      <button id="t2" onclick="tab('tcp')">👥 TCP <span class="cnt" id="c_tcp">0</span></button>
      <button id="t3" onclick="tab('cli')">🏢 Clientes</button>
    </div><div class="tabs">
      <button id="t4" onclick="tab('doc')">📑 Docs</button>
      <button id="t5" onclick="tab('avi')">🔔 Avisos <span class="cnt" id="c_avi">0</span></button>
      <button id="t6" onclick="tab('mas')">⚙️ Más</button>
    </div>
    <p><button class="btn sm gray" onclick="refresh()">🔄 Actualizar</button>
    <label style="font-weight:normal"><input type="checkbox" id="aauto" style="width:auto" checked> auto 8s</label>
    <button class="btn sm red" onclick="alogo()">Salir</button></p></div>
    <div class="box" id="v_sol"></div>
    <div class="box" id="v_tcp" style="display:none"></div>
    <div class="box" id="v_cli" style="display:none"></div>
    <div class="box" id="v_doc" style="display:none"></div>
    <div class="box" id="v_avi" style="display:none"></div>
    <div class="box" id="v_mas" style="display:none"></div>
    </div></div>
    <script>
    var BASE='';
    var TCPS=[];
    function ahd(){return {'Content-Type':'application/json','X-Admin-Token':localStorage.getItem('fw_atok')||''};}
    function atok(){return localStorage.getItem('fw_atok')||'';}
    function alogin(){fetch(BASE+'/api/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:document.getElementById('a_user').value,password:document.getElementById('a_pass').value})}).then(r=>r.json()).then(j=>{if(j.ok){localStorage.setItem('fw_atok',j.token);showApp();}else{alert(j.error||'Error');}});}
    function alogo(){localStorage.removeItem('fw_atok');location.reload();}
    function showApp(){document.getElementById('alog').style.display='none';document.getElementById('aapp').style.display='';refresh();}
    function tab(t){CUR=t;['sol','tcp','cli','doc','avi','mas'].forEach(function(x){document.getElementById('v_'+x).style.display=(x===t)?'':'none';});var m={sol:'t1',tcp:'t2',cli:'t3',doc:'t4',avi:'t5',mas:'t6'};for(var k in m){document.getElementById(m[k]).className=(k===t)?'on':'';}refreshTab(t,false);}
    var CUR='sol';
    function snap(){var o={};document.querySelectorAll('#aapp input,#aapp select,#aapp textarea').forEach(function(e){if(!e.id||e.type==='file'){return;}o[e.id]=e.type==='checkbox'?e.checked:e.value;});return o;}
    function rest(s){for(var k in s){var e=document.getElementById(k);if(!e){continue;}if(e.type==='checkbox'){e.checked=s[k];}else{e.value=s[k];}}}
    function refreshTab(t,auto){var map={sol:sols,tcp:tcps,cli:clis,doc:docs,avi:avis,mas:mas};if(auto){var v=document.getElementById('v_'+t);if(v.contains(document.activeElement)){return;}var det=v.querySelector('details');if(det&&det.open){return;}}map[t]();}
    function refresh(){var y=window.scrollY;resumen();['sol','tcp','cli','doc','avi','mas'].forEach(function(t){refreshTab(t,false);});window.scrollTo(0,y);}
    setInterval(function(){try{if(document.getElementById('aauto').checked&&localStorage.getItem('fw_atok')){resumen();refreshTab(CUR,true);}}catch(e){}},8000);
    function resumen(){fetch(BASE+'/api/admin/resumen',{headers:ahd()}).then(r=>r.json()).then(j=>{if(!j.ok){return;}var s=j.resumen;document.getElementById('ares').innerHTML='<br><small>TCP:'+s.tcp_total+' · Act:'+s.tcp_activos+' · Pend:'+s.tcp_pendientes+' · Enviados:'+s.enviados+' · Cobrado:'+s.cobrado+'</small>';document.getElementById('c_sol').textContent=s.solicitudes;document.getElementById('c_tcp').textContent=s.tcp_pendientes;document.getElementById('c_avi').textContent=s.notif_no_leidas;});}
    function sols(){fetch(BASE+'/api/admin/solicitudes',{headers:ahd()}).then(r=>r.json()).then(j=>{var h='<h3>📥 Solicitudes</h3>';(j.solicitudes||[]).forEach(function(d){h+='<div class=doc><b>#'+d.id+' '+d.tipo.toUpperCase()+'</b> · '+d.codigo+' '+d.nombre_apellidos+'<br>Cliente: '+(d.empresa||'—')+' · Contrato: '+(d.contrato_no||'—')+'<br>';d.items.forEach(function(i){h+='<small>• '+i.descripcion+' x'+i.cantidad+' @'+i.precio+'</small><br>';});h+='<button class="btn sm" onclick="gen('+d.id+')">⚡ Generar y enviar</button> <button class="btn sm red" onclick="anu('+d.id+')">Anular</button></div>';});if(!(j.solicitudes||[]).length){h+='<p>Ninguna pendiente. 🎉</p>';}document.getElementById('v_sol').innerHTML=h;});}
    function gen(id){if(!confirm('¿Generar y enviar #'+id+'? (descuenta 1 doc)')){return;}fetch(BASE+'/api/admin/generar/'+id,{method:'POST',headers:ahd()}).then(r=>r.json()).then(j=>{alert(j.mensaje||j.error);refresh();});}
    function anu(id){if(!confirm('¿Anular #'+id+'?')){return;}fetch(BASE+'/api/admin/documentos/'+id+'/anular',{method:'POST',headers:ahd()}).then(r=>r.json()).then(j=>{refresh();});}
    function tcps(){fetch(BASE+'/api/admin/tcp',{headers:ahd()}).then(r=>r.json()).then(j=>{TCPS=j.tcp||[];var h='<h3>👥 TCPs</h3><details><summary>＋ Nuevo / Editar TCP</summary><input type=hidden id=te_id><div><label>Nombre*</label><input id=te_nom></div><div class=frow><div><label>CI</label><input id=te_ci></div><div><label>Tel</label><input id=te_tel></div></div><div><label>Dirección</label><input id=te_dir></div><div class=frow><div><label>Cuenta CUP</label><input id=te_cup></div><div><label>NIT</label><input id=te_nit></div></div><div><label>Agencia</label><input id=te_ag></div><div><label>Código barra</label><input id=te_cb></div><button class="btn sm" onclick="teSave()">Guardar</button> <button class="btn sm gray" onclick="teClear()">Limpiar</button></details>';TCPS.forEach(function(t){h+='<div class=doc><b>'+t.codigo+'</b> '+t.nombre_apellidos+' <span class="pill p-'+t.estado+'">'+t.estado+'</span><br><small>Docs:'+t.docs_disponibles+' · Vence:'+(t.plan_fin||'-')+' · Tel:'+(t.telefono||'-')+'</small><br>';if(t.estado!=='activo'){h+='<button class="btn sm" onclick="act('+t.id+',\\'plan\\')">⚡ Plan</button> ';}h+='<button class="btn sm amber" onclick="act('+t.id+',\\'extra\\')">+ Extra</button> <button class="btn sm gray" onclick="teLoad('+t.id+')">✏️</button> ';if(t.estado==='activo'){h+='<button class="btn sm red" onclick="susp('+t.id+')">Suspender</button>';}h+='<br><small>Cuño:</small> <input type=file id=cq'+t.id+' accept="image/*" style="width:150px;display:inline"> <small>Firma:</small> <input type=file id=fm'+t.id+' accept="image/*" style="width:150px;display:inline"> <button class="btn sm gray" onclick="upImg('+t.id+')">Subir</button></div>';});var _s=snap();document.getElementById('v_tcp').innerHTML=h;rest(_s);});}
    function act(id,modo){if(!confirm((modo==='extra'?'Recarga EXTRA':'Activar PLAN BASE')+'?')){return;}fetch(BASE+'/api/admin/activar/'+id,{method:'POST',headers:ahd(),body:JSON.stringify({modo:modo})}).then(r=>r.json()).then(j=>{alert(j.mensaje||j.error);refresh();});}
    function susp(id){if(!confirm('¿Suspender?')){return;}fetch(BASE+'/api/admin/tcp/'+id+'/suspender',{method:'POST',headers:ahd()}).then(r=>r.json()).then(j=>{refresh();});}
    function teLoad(id){fetch(BASE+'/api/admin/tcp/'+id,{headers:ahd()}).then(r=>r.json()).then(j=>{var t=j.tcp;document.getElementById('te_id').value=t.id;document.getElementById('te_nom').value=t.nombre_apellidos||'';document.getElementById('te_ci').value=t.ci||'';document.getElementById('te_tel').value=t.telefono||'';document.getElementById('te_dir').value=t.direccion||'';document.getElementById('te_cup').value=t.cuenta_cup||'';document.getElementById('te_nit').value=t.nit||'';document.getElementById('te_ag').value=t.agencia||'';document.getElementById('te_cb').value=t.codigo_barra||'';window.scrollTo(0,0);alert('Datos cargados en el formulario de arriba. Edite y Guardar.');});}
    function teClear(){['te_id','te_nom','te_ci','te_tel','te_dir','te_cup','te_nit','te_ag','te_cb'].forEach(function(i){document.getElementById(i).value='';});}
    function teSave(){var id=document.getElementById('te_id').value;var d={nombre_apellidos:document.getElementById('te_nom').value,ci:document.getElementById('te_ci').value,telefono:document.getElementById('te_tel').value,direccion:document.getElementById('te_dir').value,cuenta_cup:document.getElementById('te_cup').value,nit:document.getElementById('te_nit').value,agencia:document.getElementById('te_ag').value,codigo_barra:document.getElementById('te_cb').value};var url=id?BASE+'/api/admin/tcp/'+id:BASE+'/api/admin/tcp';fetch(url,{method:id?'PUT':'POST',headers:ahd(),body:JSON.stringify(d)}).then(r=>r.json()).then(j=>{alert(j.ok?'Guardado':(j.error||'Error'));if(j.ok){teClear();refresh();}});}
    function upImg(id){var fd=new FormData();var a=document.getElementById('cq'+id);var b=document.getElementById('fm'+id);if(a&&a.files[0]){fd.append('cuno',a.files[0]);}if(b&&b.files[0]){fd.append('firma',b.files[0]);}if(!a.files[0]&&!b.files[0]){alert('Elija cuño y/o firma');return;}fetch(BASE+'/api/admin/tcp/'+id+'/imagen',{method:'POST',headers:{'X-Admin-Token':atok()},body:fd}).then(r=>r.json()).then(j=>{alert(j.mensaje||j.error);});}
    var CLIF='';function clis(){var h='<h3>🏢 Clientes finales</h3><details><summary>＋ Nuevo / Editar</summary><input type=hidden id=ce_id><div><label>TCP</label><select id=ce_tcp></select></div><div><label>Empresa*</label><input id=ce_emp></div><div class=frow><div><label>CUP</label><input id=ce_cup></div><div><label>CUC</label><input id=ce_cuc></div></div><div><label>Agencia</label><input id=ce_ag></div><div class=frow><div><label>Código</label><input id=ce_cod></div><div><label>NIT</label><input id=ce_nit></div></div><div><label>WhatsApp</label><input id=ce_wa></div><button class="btn sm" onclick="ceSave()">Guardar</button></details><div><label>Filtrar por TCP</label><select id=ce_f onchange="CLIF=this.value;clis()"><option value="">Todos</option></select></div><div id=ce_list></div>';var _s=snap();document.getElementById('v_cli').innerHTML=h;var s=document.getElementById('ce_tcp');TCPS.forEach(function(t){var o=document.createElement('option');o.value=t.id;o.textContent=t.codigo+' '+t.nombre_apellidos;s.appendChild(o);});var f=document.getElementById('ce_f');TCPS.forEach(function(t){var o=document.createElement('option');o.value=t.id;o.textContent=t.codigo+' '+t.nombre_apellidos;f.appendChild(o);});f.value=CLIF;rest(_s);fetch(BASE+'/api/admin/clientes'+(CLIF?'?tcp='+CLIF:''),{headers:ahd()}).then(r=>r.json()).then(j=>{var h='';(j.clientes||[]).forEach(function(x){h+='<div class=doc><b>'+x.empresa+'</b> <small>('+x.codigo+')</small><br><small>WA:'+(x.telefono_whatsapp||'-')+' · NIT:'+(x.nit||'-')+'</small><br><button class="btn sm gray" onclick="ceLoad('+x.id+')">✏️</button> <button class="btn sm red" onclick="ceDel('+x.id+')">X</button></div>';});document.getElementById('ce_list').innerHTML=h||'<p>Ninguno</p>';});}
    function ceSave(){var id=document.getElementById('ce_id').value;var d={tcp_id:document.getElementById('ce_tcp').value,empresa:document.getElementById('ce_emp').value,cuenta_cup:document.getElementById('ce_cup').value,cuenta_cuc:document.getElementById('ce_cuc').value,agencia:document.getElementById('ce_ag').value,codigo:document.getElementById('ce_cod').value,nit:document.getElementById('ce_nit').value,telefono_whatsapp:document.getElementById('ce_wa').value};var url=id?BASE+'/api/admin/clientes/'+id:BASE+'/api/admin/clientes';fetch(url,{method:id?'PUT':'POST',headers:ahd(),body:JSON.stringify(d)}).then(r=>r.json()).then(j=>{alert(j.ok?'Guardado':(j.error||'Error'));if(j.ok){refresh();}});}
    function ceLoad(id){fetch(BASE+'/api/admin/clientes',{headers:ahd()}).then(r=>r.json()).then(j=>{var x=(j.clientes||[]).find(function(c){return c.id===id;});if(!x){return;}document.getElementById('ce_id').value=x.id;document.getElementById('ce_emp').value=x.empresa||'';document.getElementById('ce_cup').value=x.cuenta_cup||'';document.getElementById('ce_cuc').value=x.cuenta_cuc||'';document.getElementById('ce_ag').value=x.agencia||'';document.getElementById('ce_cod').value=x.codigo||'';document.getElementById('ce_nit').value=x.nit||'';document.getElementById('ce_wa').value=x.telefono_whatsapp||'';window.scrollTo(0,0);alert('Cargado en el formulario. Edite y Guardar.');});}
    function ceDel(id){if(!confirm('¿Eliminar cliente?')){return;}fetch(BASE+'/api/admin/clientes/'+id,{method:'DELETE',headers:ahd()}).then(r=>r.json()).then(j=>{refresh();});}
    var DOCF='';function docs(){var h='<h3>📑 Documentos</h3><div><label>Estado</label><select id=dc_f onchange="DOCF=this.value;docs()"><option value="">Todos</option><option>solicitado</option><option>enviado</option><option>anulado</option></select></div><details><summary>＋ Documento manual (genera y envía)</summary><div class=frow><div><label>TCP</label><select id=dc_tcp onchange="dcCli()"></select></div><div><label>Tipo</label><select id=dc_tipo><option value=factura>FACTURA</option><option value=oferta>OFERTA</option></select></div></div><div><label>Cliente final</label><select id=dc_cli></select></div><div class=frow><div><label>Contrato</label><input id=dc_cont></div><div><label>Fecha</label><input id=dc_fec type=date></div></div><div id=dc_items></div><button class="btn sm gray" onclick="dcAdd()">+ artículo</button><br><button class="btn sm" onclick="dcSave()">Generar y enviar</button></details><div id=dc_list></div>';var _s=snap();document.getElementById('v_doc').innerHTML=h;document.getElementById('dc_f').value=DOCF;var s=document.getElementById('dc_tcp');TCPS.forEach(function(t){var o=document.createElement('option');o.value=t.id;o.textContent=t.codigo+' '+t.nombre_apellidos;s.appendChild(o);});var _n=DCN;dcCli();DCN=0;document.getElementById('dc_items').innerHTML='';var _k=Math.max(2,_n);for(var _i=0;_i<_k;_i++){dcAdd();}rest(_s);fetch(BASE+'/api/admin/documentos'+(DOCF?'?estado='+DOCF:''),{headers:ahd()}).then(r=>r.json()).then(j=>{var h='';(j.documentos||[]).forEach(function(d){h+='<div class=doc><b>#'+d.id+' '+(d.numero||'(s/n)')+'</b> '+d.tipo+' <span class="pill p-'+d.estado+'">'+d.estado+'</span><br><small>'+d.codigo+' · '+(d.empresa||'—')+' · '+d.total_txt+'</small><br>';if(d.pdf){h+='<a class="btn sm gray" href="'+BASE+'/api/admin/documentos/'+d.id+'/pdf?token='+atok()+'">PDF</a> ';}if(d.estado==='solicitado'){h+='<button class="btn sm" onclick="gen('+d.id+')">⚡ Generar</button> ';}if(d.estado!=='anulado'){h+='<button class="btn sm red" onclick="anu('+d.id+')">Anular</button>';}h+='</div>';});document.getElementById('dc_list').innerHTML=h||'<p>Ninguno</p>';});}
    var DCN=0;function dcAdd(){var d=document.createElement('div');d.innerHTML='<div class=frow><div><input placeholder=Descripción id=dd'+DCN+'></div><div><input value=U id=du'+DCN+' style="max-width:60px"></div><div><input type=number placeholder=Cant id=dc'+DCN+'></div><div><input type=number placeholder=Precio id=dp'+DCN+'></div></div>';document.getElementById('dc_items').appendChild(d);DCN++;}
    function dcCli(){var t=document.getElementById('dc_tcp').value;fetch(BASE+'/api/admin/clientes?tcp='+t,{headers:ahd()}).then(r=>r.json()).then(j=>{var s=document.getElementById('dc_cli');var _kv=s.value;s.innerHTML='<option value=0>— Sin cliente —</option>';(j.clientes||[]).forEach(function(x){var o=document.createElement('option');o.value=x.id;o.textContent=x.empresa;s.appendChild(o);});if(_kv){s.value=_kv;}});}
    function dcSave(){var items=[];for(var i=0;i<DCN;i++){var dd=document.getElementById('dd'+i);if(dd&&dd.value){items.push({descripcion:dd.value,um:document.getElementById('du'+i).value,cantidad:parseFloat(document.getElementById('dc'+i).value||0),precio:parseFloat(document.getElementById('dp'+i).value||0)});}}fetch(BASE+'/api/admin/documentos',{method:'POST',headers:ahd(),body:JSON.stringify({tcp_id:document.getElementById('dc_tcp').value,tipo:document.getElementById('dc_tipo').value,cliente_final_id:document.getElementById('dc_cli').value||0,contrato_no:document.getElementById('dc_cont').value,fecha:document.getElementById('dc_fec').value,items:items})}).then(r=>r.json()).then(j=>{alert(j.mensaje||j.error);refresh();});}
    function avis(){fetch(BASE+'/api/admin/notificaciones',{headers:ahd()}).then(r=>r.json()).then(j=>{var h='<h3>🔔 Avisos</h3><table>';(j.notificaciones||[]).forEach(function(n){h+='<tr><td><b>'+n.titulo+'</b><br>'+n.mensaje+'<br><small>'+n.created_at+'</small></td></tr>';});h+='</table>';document.getElementById('v_avi').innerHTML=h;});}
    function mas(){fetch(BASE+'/api/admin/config',{headers:ahd()}).then(r=>r.json()).then(j=>{var g=j.config||{};var h='<h3>💳 Recargas</h3><div id=ms_rec></div><h3>⚙️ Config</h3><div class=frow><div><label>Precio plan</label><input id=cf_pp value="'+g.precio_plan+'"></div><div><label>Docs plan</label><input id=cf_dp value="'+g.docs_plan+'"></div><div><label>Días</label><input id=cf_dia value="'+g.dias_plan+'"></div></div><div class=frow><div><label>Precio extra</label><input id=cf_pe value="'+g.precio_extra+'"></div><div><label>Docs extra</label><input id=cf_de value="'+g.docs_extra+'"></div><div><label>Gracia</label><input id=cf_gr value="'+g.dias_gracia+'"></div></div><p><label><input type=checkbox id=cf_au style="width:auto" '+(g.autogenerar==='1'?'checked':'')+'> Autogenerar solicitudes</label></p><button class="btn sm" onclick="cfSave()">Guardar config</button><h3>🔑 Clave admin</h3><div class=frow><div><label>Actual</label><input id=pw_o type=password></div><div><label>Nueva</label><input id=pw_n type=password></div></div><button class="btn sm gray" onclick="pwSave()">Cambiar clave</button>';var _s=snap();document.getElementById('v_mas').innerHTML=h;rest(_s);fetch(BASE+'/api/admin/recargas',{headers:ahd()}).then(r=>r.json()).then(k=>{var t='<table><tr><th>Fecha</th><th>TCP</th><th>Tipo</th><th>Monto</th></tr>';(k.recargas||[]).slice(0,20).forEach(function(x){t+='<tr><td><small>'+x.fecha+'</small></td><td>'+x.codigo+'</td><td>'+x.tipo+'</td><td>'+x.monto_txt+'</td></tr>';});t+='</table>';document.getElementById('ms_rec').innerHTML=t;});});}
    function cfSave(){fetch(BASE+'/api/admin/config',{method:'PUT',headers:ahd(),body:JSON.stringify({precio_plan:document.getElementById('cf_pp').value,docs_plan:document.getElementById('cf_dp').value,dias_plan:document.getElementById('cf_dia').value,precio_extra:document.getElementById('cf_pe').value,docs_extra:document.getElementById('cf_de').value,dias_gracia:document.getElementById('cf_gr').value,autogenerar:document.getElementById('cf_au').checked?'1':'0'})}).then(r=>r.json()).then(j=>{alert(j.ok?'Guardado':'Error');});}
    function pwSave(){fetch(BASE+'/api/admin/password',{method:'POST',headers:ahd(),body:JSON.stringify({username:document.getElementById('a_user').value,old:document.getElementById('pw_o').value,new:document.getElementById('pw_n').value})}).then(r=>r.json()).then(j=>{alert(j.mensaje||j.error);});}
    (function(){if(localStorage.getItem('fw_atok')){showApp();}})();
    </script>"""
    return page("Simulador App Admin", c, "simad")

# ---------- main ----------
if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
