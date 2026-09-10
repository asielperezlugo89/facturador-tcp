# Administración del Panel Web

## Acceso

```
https://SU-DOMINIO/login
Usuario: admin
Contraseña: admin123 (cambiar en Config después del primer login)
```

## Panel de control principal (`/`)

El dashboard muestra tarjetas resumen:

| Tarjeta | Descripción |
|---|---|
| TCP totales | Total de trabajadores registrados |
| Activos | TCP con plan vigente |
| Pendientes | TCP esperando activación |
| Solicitudes | Documentos pendientes de generar |
| Enviados | Documentos generados y enviados |
| Cobrado | Total de dinero recaudado |

### Accesos rápidos del dashboard

- **Sim APK cliente** (`/simulador`) — Simulador web de la app del TCP
- **Sim App admin** (`/simulador-admin`) — Simulador web de la app del admin

---

## Gestión de TCP (`/tcp`)

Lista de todos los trabajadores TCP con sus datos y estado.

### Acciones disponibles

| Acción | Descripción |
|---|---|
| **Ver ficha** | Abre la ficha completa del TCP con todos sus datos |
| **Activar plan** | Asigna plan base: 100 docs / 30 días / 1000 CUP |
| **Recarga extra** | +50 docs / 500 CUP (no extiende el plazo) |
| **Editar** | Modificar datos personales (nombre, CI, teléfono, etc.) |
| **Suspender** | Desactivar la cuenta manualmente |
| **Subir cuño** | Imagen PNG del sello/cuño del TCP |
| **Subir firma** | Imagen PNG de la firma del TCP |

### Estados de un TCP

| Estado | Significado |
|---|---|
| **pendiente** | Registrado desde la APK, esperando activación |
| **activo** | Plan vigente, puede solicitar documentos |
| **gracia** | Plan vencido, 15 días para recargar |
| **suspendido** | Desactivado manualmente por el admin |
| **vencido** | Sin recarga en gracia → docs=0 |

---

## Gestión de clientes (`/clientes`)

Lista de clientes finales (empresas/ personas para las que el TCP factura).

### Acciones

| Acción | Descripción |
|---|---|
| **Crear** | Nuevo cliente final (empresa, NIT, datos bancarios) |
| **Editar** | Modificar datos del cliente |
| **Eliminar** | Borrar cliente del sistema |

### Campos de un cliente final

- Empresa (requerido)
- NIT
- Cuenta CUP
- Cuenta CUC
- Agencia bancaria
- Código
- WhatsApp
- Dirección
- Notas

---

## Gestión de documentos (`/documentos`)

Lista de todas las facturas y ofertas comerciales.

### Filtros

- Por estado: `solicitado`, `enviado`, `anulado`
- Por TCP específico

### Acciones por documento

| Acción | Descripción |
|---|---|
| **Crear manual** | Generar documento directamente sin solicitud previa |
| **Generar PDF** | Convierte solicitud en documento enviado (descuenta 1 doc) |
| **Ver PDF** | Abrir/download del PDF generado |
| **Anular** | Marcar como anulado (no se puede deshacer) |

### Estados de un documento

| Estado | Significado |
|---|---|
| **solicitado** | TCP lo pidió desde la APK, pendiente de generar |
| **enviado** | PDF generado y disponible para descarga |
| **anulado** | Cancelado por el admin |

### Crear documento manual

1. Click "Crear documento manual"
2. Seleccionar TCP
3. Seleccionar tipo (factura u oferta)
4. Seleccionar cliente final (opcional)
5. Agregar artículos (descripción, unidad de medida, cantidad, precio)
6. Guardar → se genera el PDF inmediatamente

---

## Recargas (`/recargas`)

Historial de todas las transacciones de facturación.

| Columna | Descripción |
|---|---|
| Fecha | Fecha de la transacción |
| Código | Código del TCP (ej: TCP-001) |
| Tipo | "plan" o "extra" |
| Monto | Cantidad cobrada |

---

## Notificaciones (`/notificaciones`)

Sistema de avisos internos. Tipos de notificación:

| Tipo | Ejemplo |
|---|---|
| **registro** | "TCP-003 María García se ha registrado" |
| **activacion** | "Su cuenta ha sido activada" |
| **documento** | "Su factura F-0001 está lista" |
| **recarga** | "Recarga exitosa: +50 docs" |
| **suspension** | "Cuenta suspendida" |
| **gracia** | "Su plan ha vencido. Tiene 15 días para recargar." |
| **vencimiento** | "Período de gracia vencido. Cuenta desactivada." |

---

## Configuración (`/config`)

### Parámetros del sistema

| Parámetro | Default | Descripción |
|---|---|---|
| Precio plan | 1000 CUP | Costo del plan base |
| Docs plan | 100 | Documentos incluidos en el plan |
| Días plan | 30 | Duración del plan en días |
| Precio extra | 500 CUP | Costo de la recarga extra |
| Docs extra | 50 | Documentos de la recarga extra |
| Días gracia | 15 | Días después del vencimiento para recargar |
| Autogenerar | Desactivado | Si está activo, los PDFs se generan automáticamente |

### Token admin API

El token del admin APK se muestra en Config. Se puede rotar con el botón "Rotar token". La nueva APK debe re-login para obtener el nuevo token.

### Cambiar contraseña

1. Ir a Config
2. Ingresar contraseña actual
3. Ingresar nueva contraseña (mínimo 4 caracteres)
4. Guardar

---

## Simuladores web

### Simulador APK Cliente (`/simulador`)

Réplica exacta de la app del TCP en el navegador. Permite:
- Registro de prueba
- Consulta de estado
- Solicitud de documentos
- Descarga de PDFs
- Ver notificaciones

### Simulador APK Admin (`/simulador-admin`)

Réplica de la app del administrador con 6 pestañas:
1. **Solicitudes** — Ver y generar documentos pendientes
2. **TCP** — Gestionar trabajadores
3. **Clientes** — Gestionar clientes finales
4. **Documentos** — Ver todos los documentos
5. **Avisos** — Notificaciones del admin
6. **Más** — Configuración, recargas, cambiar contraseña

---

## Tips de uso diario

1. **Revisar solicitudes pendientes** al inicio del día en la pestaña de documentos
2. **Activar TCPs pendientes** que se han registrado recientemente
3. **Monitorear notificaciones** para detectar nuevos registros o problemas
4. **Rotar el token admin** periódicamente por seguridad
5. **Hacer backup de `data.db`** regularmente (solo en local)
