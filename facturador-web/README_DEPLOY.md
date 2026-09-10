# Facturador TCP — Parte 1: Web + API (Wasmer)

Sistema de facturación para TCP (Cuba): web administradora + API REST para APK cliente y APK admin.
PDF con formato de FACTURA DE VENTA y OFERTA COMERCIAL. Renta por documentos con activación,
recargas, gracia y baja automática.

## Archivos
| Archivo | Qué es |
|---|---|
| `app.py` | Web admin + API cliente + API admin + simuladores |
| `db.py` | BD: MySQL en Wasmer (`DB_*`) o SQLite local (`data.db`) |
| `pdfgen.py` | Generador PDF (fpdf2, sin dependencias nativas) |
| `requirements.txt` | Deps Python (Flask, fpdf2, PyMySQL, gunicorn) |
| `test_api.py` | Prueba integral API cliente (18 checks, auto-limpia) |
| `test_admin_api.py` | Prueba integral API admin (18 checks, auto-limpia) |

## Probar local
```bash
cd facturador-web
pip install -r requirements.txt
python3 app.py
# http://127.0.0.1:5000  →  admin / admin123
python3 test_api.py
python3 test_admin_api.py
```
- Web: panel, TCPs (activar plan/extra/suspender, cuño+firma PNG), clientes finales,
  documentos (solicitudes, manual, PDF, anular), recargas, notificaciones, config.
- Simuladores: `/simulador` (APK cliente) y `/simulador-admin` (APK admin, 6 pestañas).
- La sesión web funciona con cookies y sin cookies (`?sk=`, para iframes).

## Subir a Wasmer
Wasmer detecta Python/Flask solo con `requirements.txt` + `app.py` y adjunta
MySQL/PostgreSQL con `DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD`.
[1](https://docs.wasmer.io/edge/learn/supported-frameworks-and-languages/)

1. Cuenta en https://wasmer.io y dominio (ej `mi-facturador.wasmer.app`).
2. Suba esta carpeta a GitHub (**sin** `data.db`, ya está en `.gitignore`).
3. Wasmer → New App → From GitHub → elija el repo (detección Python/Flask automática).
4. Variables: `SECRET_KEY` = texto largo aleatorio. Comando si lo pide:
   `gunicorn app:app --bind 0.0.0.0:$PORT --workers 2`.
5. Despliegue. La primera vez crea tablas + admin inicial.

## Después del despliegue (checklist)
- [ ] Entrar `https://SU-DOMINIO/login` → **admin / admin123**, cambiar clave en Config.
- [ ] Copiar de Config: URL base + token admin API (para las APK).
- [ ] Revisar precios/días/gracia y `autogenerar` según prefiera.
- [ ] Probar ciclo: registrar TCP de prueba → activar → solicitar doc → generar → PDF.
- [ ] Las APK apuntan a `https://SU-DOMINIO` (endpoints abajo).

## API cliente (APK, headers `X-Token` + `X-Device`)
```
POST /api/registro                 registro (device_id único)
POST /api/estado                   poll activación/saldo/vigencia
GET  /api/mis-clientes             clientes finales del TCP
POST /api/solicitar-documento      pide factura/oferta (no consume hasta generar)
GET  /api/mis-documentos           lista con estado y totales
GET  /api/documentos/<id>/pdf      descarga PDF (o ?token=&device=)
GET  /api/notificaciones           avisos (documento listo, activación, recarga…)
POST /api/notificaciones/leer
GET  /api/cron                     barrido de vencimientos (llamar 1 vez/día)
```

## API admin (APK admin, header `X-Admin-Token`)
```
POST /api/admin/login              → token
GET  /api/admin/resumen            contadores
GET  /api/admin/tcp  (+/<id>, POST, PUT, /suspender, /imagen)
POST /api/admin/activar/<id>       {modo: plan|extra}
GET  /api/admin/solicitudes        pendientes con artículos
POST /api/admin/generar/<id>       genera+envía (descuenta 1)
GET  /api/admin/clientes           CRUD (+POST, PUT, DELETE)
GET  /api/admin/documentos         (+POST manual, /anular, /<id>/pdf)
GET  /api/admin/recargas  |  GET/PUT /api/admin/config  |  POST /api/admin/password
GET  /api/admin/notificaciones
```

## Renta (lógica)
- Plan base: 100 docs / 1000 CUP / 30 días. Extra: 50 docs / 500 (no extiende).
- Gracia 15 días tras vencer: sigue activo con aviso; si recarga, conserva saldo.
- Sin recarga en gracia → docs=0 + desactivado (solo el admin reactiva con plan).

## Si olvida la clave admin
Local: borre `data.db` y reinicie (se recrea admin/admin123, **pierde datos**).
Wasmer/consola: `python3 -c "from werkzeug.security import generate_password_hash as g;import db;db.execute(\"UPDATE admin_users SET password_hash=? WHERE username='admin'\",(g('NUEVA'),));print('ok')"`
