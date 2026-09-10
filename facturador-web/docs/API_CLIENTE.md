# API Cliente — Referencia completa

La API cliente es consumida por la APK del trabajador TCP. Todos los endpoints requieren headers de autenticación específicos.

## Autenticación

```
X-Token: <token_del_tcp>
X-Device: <device_id_del_telefono>
```

El `device_id` es el Android ID del dispositivo. Si no coincide con el registrado, la petición es rechazada.

---

## Endpoints

### 1. POST `/api/registro`

Registra un nuevo TCP desde la APK.

**Request:**
```json
{
  "nombre_apellidos": "Juan Pérez López",
  "device_id": "abc123def456",
  "ci": "98012345678",
  "telefono": "5555-1234",
  "direccion": "Calle 123 #456",
  "cuenta_cup": "1234567890",
  "nit": "98012345678",
  "device_info": "Samsung Galaxy S21"
}
```

**Campos requeridos:** `nombre_apellidos`, `device_id`

**Response (200):**
```json
{
  "ok": true,
  "token": "a1b2c3d4e5f6...",
  "codigo": "TCP-001",
  "tcp_id": 1,
  "estado": "pendiente",
  "mensaje": "Registro exitoso. Esperando activación del administrador."
}
```

**Error (400):**
```json
{
  "ok": false,
  "error": "Faltan nombre_apellidos o device_id"
}
```

---

### 2. POST `/api/estado`

Consulta el estado de la cuenta (saldo de docs, vigencia, período de gracia).

**Headers:** `X-Token`, `X-Device`

**Response (200):**
```json
{
  "ok": true,
  "codigo": "TCP-001",
  "estado": "activo",
  "docs": 85,
  "plan_fin": "2026-10-10",
  "activo": true,
  "en_gracia": false,
  "mensaje": "Activo. 85 docs disponibles. Vence: 10/10/2026"
}
```

---

### 3. GET `/api/mis-clientes`

Lista los clientes finales registrados por el TCP.

**Headers:** `X-Token`, `X-Device`

**Response (200):**
```json
{
  "ok": true,
  "clientes": [
    {
      "id": 1,
      "empresa": "Empresa ABC",
      "cuenta_cup": "1234567890",
      "cuenta_cuc": "",
      "agencia": "Banco Metropolitano",
      "codigo": "CLI-001",
      "nit": "98012345678",
      "telefono_whatsapp": "5555-6789",
      "direccion": "Ave 123"
    }
  ]
}
```

---

### 4. POST `/api/solicitar-documento`

Solicita una factura u oferta comercial.

**Headers:** `X-Token`, `X-Device`

**Request:**
```json
{
  "tipo": "factura",
  "cliente_final_id": 1,
  "contrato_no": "CONT-2026-001",
  "fecha": "2026-09-10",
  "numero_blanco": false,
  "fecha_blanco": false,
  "items": [
    {
      "descripcion": "Servicio de consultoría",
      "um": "U",
      "cantidad": 2,
      "precio": 500.00
    },
    {
      "descripcion": "Material de oficina",
      "um": "U",
      "cantidad": 10,
      "precio": 25.50
    }
  ]
}
```

**Campos:** `tipo` ("factura" o "oferta"), `items` (array con al menos 1 elemento)

**Response (200):**
```json
{
  "ok": true,
  "doc_id": 1,
  "estado": "solicitado",
  "mensaje": "Solicitud registrada. Esperando generación del administrador."
}
```

Si `autogenerar` está activado:
```json
{
  "ok": true,
  "doc_id": 1,
  "estado": "enviado",
  "mensaje": "Documento generado automáticamente.",
  "docs_restantes": 84
}
```

---

### 5. GET `/api/mis-documentos`

Lista todos los documentos del TCP con estado y totales.

**Headers:** `X-Token`, `X-Device`

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
      "created_at": "2026-09-10 14:30:00",
      "generated_at": "2026-09-10 15:00:00",
      "empresa": "Empresa ABC",
      "pdf": true
    }
  ]
}
```

---

### 6. GET `/api/documentos/<id>/pdf`

Descarga el PDF de un documento específico.

**Headers:** `X-Token`, `X-Device`

**Response:** Archivo PDF binario (`Content-Type: application/pdf`)

**Alternativa sin headers (para visor):**
```
GET /api/documentos/1/pdf?token=<token>&device=<device_id>
```

---

### 7. GET `/api/notificaciones`

Lista las notificaciones del TCP.

**Headers:** `X-Token`, `X-Device`

**Response (200):**
```json
{
  "ok": true,
  "notificaciones": [
    {
      "id": 1,
      "titulo": "Documento listo",
      "mensaje": "Su factura F-0001 ha sido generada y está lista para descargar.",
      "tipo": "documento",
      "leida": 0,
      "created_at": "2026-09-10 15:00:00"
    }
  ]
}
```

---

### 8. POST `/api/notificaciones/leer`

Marca todas las notificaciones como leídas.

**Headers:** `X-Token`, `X-Device`

**Response (200):**
```json
{
  "ok": true
}
```

---

### 9. GET `/api/cron`

Barrido de vencimientos. Diseñado para ser llamado una vez al día (por un cron job o servicio externo).

**Auth:** Ninguna

**Response (200):**
```json
{
  "ok": true,
  "bajas": 3
}
```

Devuelve la cantidad de cuentas dadas de baja por vencimiento.

---

## Errores comunes

| Código HTTP | Error | Causa |
|---|---|---|
| 400 | `Faltan nombre_apellidos o device_id` | Campos requeridos no enviados |
| 401 | `Token inválido` | Token no existe en la base de datos |
| 403 | `Dispositivo no coincide` | device_id no coincide con el registrado |
| 400 | `Sin docs disponibles` | TCP sin saldo de documentos |
| 400 | `Cuenta vencida` | Plan vencido fuera de período de gracia |
| 400 | `Cuenta suspendida` | TCP suspendido por el admin |
| 404 | `No existe` | Documento o cliente no encontrado |

## Flujo típico de uso

```
1. Registro:     POST /api/registro
2. Poll estado:  POST /api/estado  (periódicamente)
3. Ver clientes: GET  /api/mis-clientes
4. Solicitar:    POST /api/solicitar-documento
5. Ver docs:     GET  /api/mis-documentos
6. Descargar:    GET  /api/documentos/<id>/pdf
7. Avisos:       GET  /api/notificaciones
8. Marcar leído: POST /api/notificaciones/leer
```
