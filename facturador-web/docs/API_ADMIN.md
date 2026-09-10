# API Admin — Referencia completa

La API admin es consumida por la APK del administrador y el panel web. Todos los endpoints (excepto login) requieren el header `X-Admin-Token`.

## Autenticación

```
X-Admin-Token: <token_admin>
```

El token se obtiene con el endpoint de login y es el mismo para todo el sistema.

---

## Endpoints

### 1. POST `/api/admin/login`

Autenticación del administrador.

**Request:**
```json
{
  "username": "admin",
  "password": "admin123"
}
```

**Response (200):**
```json
{
  "ok": true,
  "token": "a1b2c3d4e5f6g7h8i9j0..."
}
```

**Error (401):**
```json
{
  "ok": false,
  "error": "Credenciales inválidas"
}
```

---

### 2. GET `/api/admin/resumen`

Resumen del dashboard (contadores principales).

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "resumen": {
    "tcp_total": 25,
    "tcp_activos": 18,
    "tcp_pendientes": 3,
    "solicitudes": 5,
    "enviados": 142,
    "cobrado": 125000.00,
    "notif_no_leidas": 2
  }
}
```

---

### 3. GET `/api/admin/tcp`

Lista todos los clientes TCP registrados.

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "tcp": [
    {
      "id": 1,
      "codigo": "TCP-001",
      "nombre_apellidos": "Juan Pérez López",
      "telefono": "5555-1234",
      "estado": "activo",
      "docs_disponibles": 85,
      "plan_fin": "2026-10-10",
      "device_id": "abc123def456"
    }
  ]
}
```

---

### 4. POST `/api/admin/tcp`

Crea un nuevo cliente TCP.

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "nombre_apellidos": "María García Torres",
  "ci": "98012345679",
  "telefono": "5555-5678",
  "direccion": "Calle 456 #789",
  "email": "maria@email.com",
  "cuenta_cup": "0987654321",
  "agencia": "Banco Popular",
  "nit": "98012345679",
  "cargo": "TCP"
}
```

**Campos requeridos:** `nombre_apellidos`

**Response (200):**
```json
{
  "ok": true,
  "tcp_id": 2
}
```

---

### 5. GET `/api/admin/tcp/<tcp_id>`

Obtiene el detalle de un TCP específico.

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "tcp": {
    "id": 1,
    "codigo": "TCP-001",
    "nombre_apellidos": "Juan Pérez López",
    "ci": "98012345678",
    "telefono": "5555-1234",
    "direccion": "Calle 123",
    "email": "juan@email.com",
    "cuenta_cup": "1234567890",
    "agencia": "Banco Metropolitano",
    "nit": "98012345678",
    "estado": "activo",
    "docs_disponibles": 85,
    "plan_inicio": "2026-09-01",
    "plan_fin": "2026-10-10",
    "device_id": "abc123def456"
  }
}
```

---

### 6. PUT `/api/admin/tcp/<tcp_id>`

Actualiza los datos de un TCP (actualización parcial).

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "telefono": "5555-9999",
  "direccion": "Nueva dirección 789"
}
```

**Response (200):**
```json
{
  "ok": true
}
```

---

### 7. POST `/api/admin/activar/<tcp_id>`

Activa un plan para un TCP.

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request (plan base):**
```json
{}
```

**Request (recarga extra):**
```json
{
  "modo": "extra"
}
```

**Response (plan base):**
```json
{
  "ok": true,
  "mensaje": "Activado: 100 docs hasta 10/10/2026"
}
```

**Response (extra):**
```json
{
  "ok": true,
  "mensaje": "Recarga: +50 docs. Saldo: 135."
}
```

---

### 8. POST `/api/admin/tcp/<tcp_id>/suspender`

Suspende la cuenta de un TCP.

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "mensaje": "Suspendido."
}
```

---

### 9. POST `/api/admin/tcp/<tcp_id>/imagen`

Sube imágenes de cuño y/o firma para un TCP.

**Headers:** `X-Admin-Token`, `Content-Type: multipart/form-data`

**Request (multipart):**
- `cuno`: Archivo PNG del cuño
- `firma`: Archivo PNG de la firma

**Alternativa JSON (base64):**
```json
{
  "cuno_b64": "iVBORw0KGgoAAAANS...",
  "cuno_b64_nombre": "cuno.png",
  "firma_b64": "iVBORw0KGgoAAAANS...",
  "firma_b64_nombre": "firma.png"
}
```

**Response (200):**
```json
{
  "ok": true,
  "mensaje": "Imágenes guardadas."
}
```

---

### 10. GET `/api/admin/solicitudes`

Lista todas las solicitudes de documentos pendientes (estado = "solicitado").

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "solicitudes": [
    {
      "id": 1,
      "numero": "F-0001",
      "tipo": "factura",
      "estado": "solicitado",
      "contrato_no": "CONT-2026-001",
      "fecha": "2026-09-10",
      "items": [
        {
          "descripcion": "Servicio de consultoría",
          "um": "U",
          "cantidad": 2,
          "precio": 500.00
        }
      ],
      "created_at": "2026-09-10 14:30:00",
      "codigo": "TCP-001",
      "nombre_apellidos": "Juan Pérez López",
      "empresa": "Empresa ABC"
    }
  ]
}
```

---

### 11. POST `/api/admin/generar/<doc_id>`

Genera el PDF y envía un documento (convierte de "solicitado" a "enviado", descuenta 1 doc del saldo).

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "mensaje": "Documento F-0001 generado y enviado. Saldo: 84."
}
```

**Error:**
```json
{
  "ok": false,
  "mensaje": "Sin documentos disponibles para generar."
}
```

---

### 12. GET `/api/admin/documentos`

Lista documentos con filtros opcionales.

**Headers:** `X-Admin-Token`

**Query params:**
- `?estado=solicitado` — Filtrar por estado
- `?tcp=<tcp_id>` — Filtrar por TCP

**Response (200):**
```json
{
  "ok": true,
  "documentos": [
    {
      "id": 1,
      "numero": "F-0001",
      "tipo": "factura",
      "estado": "enviado",
      "total": 1255.00,
      "total_txt": "1 255.00",
      "fecha": "2026-09-10",
      "contrato_no": "CONT-2026-001",
      "created_at": "2026-09-10 14:30:00",
      "codigo": "TCP-001",
      "empresa": "Empresa ABC",
      "pdf": true
    }
  ]
}
```

---

### 13. POST `/api/admin/documentos`

Crea un documento manualmente y lo genera/envía inmediatamente.

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "tcp_id": 1,
  "tipo": "factura",
  "cliente_final_id": 1,
  "contrato_no": "CONT-2026-002",
  "fecha": "2026-09-10",
  "numero_blanco": false,
  "fecha_blanco": false,
  "items": [
    {
      "descripcion": "Producto A",
      "um": "U",
      "cantidad": 5,
      "precio": 100.00
    }
  ]
}
```

**Campos requeridos:** `tcp_id`, `items` (al menos 1)

**Response (200):**
```json
{
  "ok": true,
  "doc_id": 2,
  "mensaje": "Documento creado y enviado."
}
```

---

### 14. POST `/api/admin/documentos/<doc_id>/anular`

Anula un documento (estado → "anulado").

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true
}
```

---

### 15. GET `/api/admin/documentos/<doc_id>/pdf`

Descarga el PDF de un documento.

**Headers:** `X-Admin-Token`

**Response:** Archivo PDF binario (`Content-Type: application/pdf`)

**Alternativa:** `GET /api/admin/documentos/<doc_id>/pdf?token=<token>`

---

### 16. GET `/api/admin/clientes`

Lista todos los clientes finales. Opcionalmente filtra por TCP.

**Headers:** `X-Admin-Token`

**Query params:** `?tcp=<tcp_id>`

**Response (200):**
```json
{
  "ok": true,
  "clientes": [
    {
      "id": 1,
      "tcp_id": 1,
      "empresa": "Empresa ABC",
      "cuenta_cup": "1234567890",
      "cuenta_cuc": "",
      "agencia": "Banco Metropolitano",
      "codigo": "CLI-001",
      "nit": "98012345678",
      "telefono_whatsapp": "5555-6789",
      "direccion": "Ave 123",
      "notas": "",
      "created_at": "2026-09-01"
    }
  ]
}
```

---

### 17. POST `/api/admin/clientes`

Crea un nuevo cliente final.

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "tcp_id": 1,
  "empresa": "Empresa XYZ",
  "cuenta_cup": "0987654321",
  "agencia": "Banco Popular",
  "codigo": "CLI-002",
  "nit": "98012345680",
  "telefono_whatsapp": "5555-4321",
  "direccion": "Calle 789"
}
```

**Campos requeridos:** `tcp_id`, `empresa`

**Response (200):**
```json
{
  "ok": true,
  "cliente_id": 2
}
```

---

### 18. PUT `/api/admin/clientes/<cid>`

Actualiza un cliente final (parcial).

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "telefono_whatsapp": "5555-0000",
  "direccion": "Nueva dirección"
}
```

**Response (200):**
```json
{
  "ok": true
}
```

---

### 19. DELETE `/api/admin/clientes/<cid>`

Elimina un cliente final.

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true
}
```

---

### 20. GET `/api/admin/recargas`

Lista el historial de recargas (últimas 100).

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "recargas": [
    {
      "id": 1,
      "tcp_id": 1,
      "tipo": "plan",
      "docs": 100,
      "monto": 1000.00,
      "monto_txt": "1 000.00",
      "fecha": "2026-09-01",
      "admin": "admin",
      "nota": "Activación plan base",
      "codigo": "TCP-001"
    }
  ]
}
```

---

### 21. GET `/api/admin/notificaciones`

Lista las notificaciones del admin (y las marca como leídas).

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "notificaciones": [
    {
      "id": 1,
      "titulo": "Nuevo registro",
      "mensaje": "TCP-003 María García se ha registrado. Pendiente activación.",
      "tipo": "registro",
      "leida": 1,
      "created_at": "2026-09-10 16:00:00",
      "extra": ""
    }
  ]
}
```

---

### 22. GET `/api/admin/config`

Obtiene la configuración del sistema.

**Headers:** `X-Admin-Token`

**Response (200):**
```json
{
  "ok": true,
  "config": {
    "precio_plan": "1000",
    "docs_plan": "100",
    "dias_plan": "30",
    "precio_extra": "500",
    "docs_extra": "50",
    "dias_gracia": "15",
    "autogenerar": "0",
    "nombre_sistema": "Facturador TCP"
  }
}
```

---

### 23. PUT `/api/admin/config`

Actualiza la configuración del sistema (parcial).

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "precio_plan": "1200",
  "autogenerar": "1"
}
```

**Response (200):**
```json
{
  "ok": true
}
```

---

### 24. POST `/api/admin/password`

Cambia la contraseña del administrador.

**Headers:** `X-Admin-Token`, `Content-Type: application/json`

**Request:**
```json
{
  "username": "admin",
  "old": "admin123",
  "new": "nueva_clave_segura"
}
```

**Campos requeridos:** `old`, `new` (mínimo 4 caracteres)

**Response (200):**
```json
{
  "ok": true,
  "mensaje": "Clave actualizada."
}
```

**Error:**
```json
{
  "ok": false,
  "error": "Clave actual incorrecta"
}
```

---

## Errores comunes

| Código HTTP | Error | Causa |
|---|---|---|
| 401 | `No autorizado` | Token admin inválido o no enviado |
| 400 | `Falta nombre_apellidos` | Campo requerido no enviado |
| 400 | `Faltan tcp_id / empresa` | Campos requeridos no enviados |
| 400 | `Sin artículos` | Array `items` vacío |
| 400 | `tcp_id inválido` | TCP no existe |
| 400 | `Clave actual incorrecta` | Contraseña vieja errónea |
| 400 | `Nueva clave muy corta` | Contraseña nueva < 4 caracteres |
| 404 | `No existe` | TCP, cliente o documento no encontrado |
| 400 | `Sin PDF` | Documento sin PDF generado |
