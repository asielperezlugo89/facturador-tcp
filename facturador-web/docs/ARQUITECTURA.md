# Arquitectura del Sistema

## Diagrama de componentes

```
┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   APK Cliente TCP   │     │   APK Admin TCP     │     │  Panel Web Admin│
│   (Kotlin/Android)  │     │   (Kotlin/Android)  │     │  (Flask HTML)   │
└─────────┬───────────┘     └─────────┬───────────┘     └────────┬────────┘
          │                           │                           │
          │ POST /api/*               │ /api/admin/*              │ HTML + JS
          │ X-Token + X-Device        │ X-Admin-Token             │ Cookie session
          │                           │                           │
          └───────────┬───────────────┴───────────────────────────┘
                      │
                      ▼
        ┌─────────────────────────────┐
        │        Flask Server         │
        │   app.py (1529 líneas)     │
        │                             │
        │  ┌──────────┐ ┌──────────┐  │
        │  │ API REST │ │ Web Admin│  │
        │  │ (JSON)   │ │ (HTML)   │  │
        │  └──────────┘ └──────────┘  │
        │       │                     │
        │  ┌────▼─────┐  ┌─────────┐  │
        │  │   db.py  │  │pdfgen.py│  │
        │  └────┬─────┘  └─────────┘  │
        └───────┼─────────────────────┘
                │
                ▼
    ┌───────────────────────┐
    │    Base de Datos      │
    │ SQLite (local)        │
    │ MySQL (Wasmer Edge)   │
    └───────────────────────┘
```

## Componentes

### 1. Flask Server (`app.py`)

Servidor monolítico que maneja tres responsabilidades:

- **Panel Web Admin**: HTML server-side rendered con Flask templates inline
- **API Cliente** (10 endpoints): Para la APK del trabajador TCP
- **API Admin** (24 endpoints): Para la APK del administrador
- **Simuladores**: `/simulador` y `/simulador-admin` (SPAs JavaScript)

### 2. Capa de Base de Datos (`db.py`)

Doble estrategia de base de datos:

| Entorno | Base de Datos | Configuración |
|---|---|---|
| Local | SQLite (`data.db`) | Automática, cero config |
| Wasmer Edge | MySQL | Variables `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USERNAME`, `DB_PASSWORD` |

7 tablas: `admin_users`, `tcp_clientes`, `clientes_finales`, `documentos`, `recargas`, `notificaciones`, `config`

### 3. Generador PDF (`pdfgen.py`)

- Usa **fpdf2** (puro Python, sin dependencias nativas)
- Genera FACTURA DE VENTA y OFERTA COMERCIAL
- Embebe cuño (PNG) y firma (PNG) desde BLOB en la base de datos
- Compatible con Wasmer Edge (sin librerías del sistema)

## Flujo de registro de TCP

```
1. TCP descarga APK y abre
2. Ingresa datos personales (nombre, CI, teléfono, etc.)
3. APK envía POST /api/registro con device_id único
4. Servidor crea registro con estado "pendiente" + token único
5. Admin ve TCP pendiente en panel → activa plan
6. TCP recibe notificación de activación
```

## Flujo de solicitud de documento

```
1. TCP abre APK → Solicitar documento
2. Selecciona tipo (factura/oferta), cliente, fecha
3. Agrega artículos (descripción, cantidad, precio)
4. APK envía POST /api/solicitar-documento
5. Si autogenerar=ON: PDF se genera automáticamente
6. Si autogenerar=OFF: queda como "solicitado" → admin genera con POST /api/admin/generar/<id>
7. TCP recibe notificación y puede descargar PDF
```

## Ciclo de vida de suscripción

```
┌──────────┐    Admin activa    ┌──────────┐    30 días     ┌──────────┐
│ PENDIENT │ ──────────────────→│  ACTIVO  │ ─────────────→│ VENCIDO  │
└──────────┘                    └──────────┘                └──────────┘
                                     │                          │
                                     │    +15 días gracia       │
                                     │    (sigue activo)        │
                                     │                          │
                                     ▼                          ▼
                               ┌──────────┐              ┌──────────┐
                               │ RECARGA  │              │BAJA AUTO │
                               │(+50 docs)│              │(docs=0)  │
                               └──────────┘              └──────────┘
```

### Estados posibles

| Estado | Descripción |
|---|---|
| `pendiente` | TCP registrado, esperando activación del admin |
| `activo` | Plan vigente, puede solicitar documentos |
| `gracia` | Plan vencido pero dentro de los 15 días de gracia |
| `suspendido` | Desactivado manualmente por el admin |
| `vencido` | Sin recarga después de gracia → docs=0, desactivado |

## Seguridad

### Device Binding

Cada cuenta TCP está vinculada al `device_id` del teléfono (Android ID). Si otro dispositivo intenta usar el mismo token, es rechazado. Esto previene el uso compartido de cuentas.

### Autenticación API

| Componente | Header | Descripción |
|---|---|---|
| APK Cliente | `X-Token` + `X-Device` | Token único por TCP + ID del dispositivo |
| APK Admin | `X-Admin-Token` | Token compartido (único para todo el sistema) |
| Panel Web | Cookie de sesión | Flask session con `?sk=TOKEN` fallback para iframes |

### Cookies para iframe

El panel admin usa cookies `Partitioned + Secure + SameSite=None` (CHIPS) cuando detecta entornos HTTPS/proxy para funcionar dentro de iframes sin bloqueos de cookies de terceros.

## Decisiones de diseño

1. **Monolito intencional**: `app.py` concentra toda la lógica para simplicidad de despliegue en Wasmer Edge (auto-detecta Flask).

2. **PDF almacenado en BD**: Los PDFs generados se guardan como BLOBs junto con un snapshot JSON de los datos del TCP/cliente al momento de generación, para preservar históricos.

3. **Sesiones sin cookies**: Para entornos donde las cookies de terceros están bloqueadas (previews en iframe), la sesión viaja por parámetro URL `?sk=TOKEN`.

4. **Generación dual**: El modo `autogenerar` permite que los PDFs se creen automáticamente al llegar la solicitud, sin necesidad de aprobación manual del admin.
