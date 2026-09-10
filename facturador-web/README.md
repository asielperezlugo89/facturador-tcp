# Facturador TCP

Sistema de facturación para TCP (Trabajadores por Cuenta Propia) en Cuba. Genera **FACTURAS DE VENTA** y **OFERTAS COMERCIALES** en PDF, con modelo de renta por documentos, activación, recargas, período de gracia y baja automática.

## Componentes

| Componente | Tecnología | Descripción |
|---|---|---|
| **Servidor Web + API** | Python / Flask | Panel admin web + API REST para APKs |
| **APK Cliente** | Kotlin / Android | App para TCP: registro, solicitudes, descarga PDF |
| **APK Admin** | Kotlin / Android | App para administrador: gestión completa del sistema |

## Características

- PDF con formato oficial cubano (FACTURA DE VENTA / OFERTA COMERCIAL)
- Cuño y firma digital embebidos en el PDF
- Registro de TCP por dispositivo (device binding)
- Plan base (100 docs / 30 días) + recargas extra (50 docs)
- Período de gracia de 15 días con avisos
- Baja automática por vencimiento
- Modo autogenerar: PDFs automáticos sin aprobación del admin
- Panel web con dashboard, gestión de TCPs, clientes, documentos, recargas, notificaciones
- Simuladores web de ambas APKs para pruebas sin dispositivo físico

## Instalación rápida

```bash
cd facturador-web
pip install -r requirements.txt
python app.py
# Abrir http://127.0.0.1:5000
# Login: admin / admin123
```

## Ejecutar pruebas

```bash
python test_api.py         # 18 checks API cliente
python test_admin_api.py   # 18 checks API admin
```

## Estructura del proyecto

```
tcp-server/
├── facturador-web/
│   ├── app.py              # Servidor principal (web + API cliente + API admin)
│   ├── db.py               # Capa de base de datos (SQLite local / MySQL Wasmer)
│   ├── pdfgen.py           # Generador PDF (fpdf2)
│   ├── requirements.txt    # Dependencias Python
│   ├── app.py              # Aplicación principal
│   ├── test_api.py         # Pruebas API cliente
│   ├── test_admin_api.py   # Pruebas API admin
│   ├── data.db             # Base de datos SQLite (solo local, en .gitignore)
│   ├── README.md           # Este archivo
│   └── docs/               # Documentación detallada
│       ├── ARQUITECTURA.md
│       ├── API_CLIENTE.md
│       ├── API_ADMIN.md
│       ├── DESPLIEGUE.md
│       ├── ADMINISTRACION.md
│       └── ANDROID.md
├── android/
│   ├── ClienteTCP/         # APK para trabajadores TCP
│   └── AdminTCP/           # APK para administrador
└── uploads/                # PDFs generados (almacenados aquí)
```

## Modelo de negocio

| Concepto | Valor |
|---|---|
| Plan base | 100 documentos / 30 días / 1000 CUP |
| Recarga extra | +50 documentos / 500 CUP (no extiende plazo) |
| Período de gracia | 15 días después del vencimiento |
| Baja automática | Sin recarga en gracia → docs=0 + desactivado |

## Documentación

- [Arquitectura del sistema](docs/ARQUITECTURA.md)
- [API Cliente (10 endpoints)](docs/API_CLIENTE.md)
- [API Admin (24 endpoints)](docs/API_ADMIN.md)
- [Despliegue (local + Wasmer)](docs/DESPLIEGUE.md)
- [Administración del panel](docs/ADMINISTRACION.md)
- [Compilación de APKs](docs/ANDROID.md)

## Despliegue en Wasmer

```bash
# Requiere cuenta en https://wasmer.io
wasmer app create --name facturador-tcp --package .
wasmer app deploy
```

Ver [guía completa de despliegue](docs/DESPLIEGUE.md).

## Credenciales por defecto

| Usuario | Contraseña | Rol |
|---|---|---|
| `admin` | `admin123` | Administrador del sistema |

> Cambiar la contraseña inmediatamente después del primer login en Config.

## Licencia

Proyecto privado. Uso interno para sistema de facturación TCP Cuba.
