# Compilación de APKs

## Requisitos

- **Android Studio** (o solo Android SDK + JDK)
- **JDK 17+** (probado con JDK 23)
- **Android SDK** (API 34)
- Variables de entorno: `JAVA_HOME`, `ANDROID_HOME`

### Verificar entorno

```bash
# Java
java -version
echo $JAVA_HOME

# Android SDK
echo $ANDROID_HOME
```

---

## Configuración del servidor

Antes de compilar, actualizar la URL del servidor en `gradle.properties` de cada proyecto:

### ClienteTCP

Editar `android/ClienteTCP/gradle.properties`:
```properties
SERVER_URL=https://SU-DOMINIO.wasmer.app
```

### AdminTCP

Editar `android/AdminTCP/gradle.properties`:
```properties
SERVER_URL=https://SU-DOMINIO.wasmer.app
```

---

## Compilar ClienteTCP

```bash
cd android/ClienteTCP

# Windows
.\gradlew.bat assembleRelease

# Linux/Mac
./gradlew assembleRelease
```

**APK resultante:**
```
app/build/outputs/apk/release/app-release-unsigned.apk
```

---

## Compilar AdminTCP

```bash
cd android/AdminTCP

# Windows
.\gradlew.bat assembleRelease

# Linux/Mac
./gradlew assembleRelease
```

**APK resultante:**
```
app/build/outputs/apk/release/app-release-unsigned.apk
```

---

## Firmar APKs (opcional)

Las APKs sin firmar se pueden instalar directamente en dispositivos de desarrollo. Para distribución:

### Generar keystore

```bash
keytool -genkey -v -keystore facturador.keystore -alias facturador -keyalg RSA -keysize 2048 -validity 10000
```

### Firmar con apksigner

```bash
# Copiar APK sin firmar
cp app/build/outputs/apk/release/app-release-unsigned.apk app-release.apk

# Firmar
apksigner sign --ks facturador.keystore --out app-release-signed.apk app-release.apk
```

### Verificar firma

```bash
apksigner verify --verbose app-release-signed.apk
```

---

## Instalar en dispositivo

### Vía ADB

```bash
adb install app-release-unsigned.apk
# o
adb install app-release-signed.apk
```

### Vía USB (modo desarrollador)

1. Activar "Opciones de desarrollador" en el teléfono
2. Activar "Depuración USB"
3. Conectar por USB
4. Ejecutar `adb install`

### Directamente en el dispositivo

1. Copiar el archivo `.apk` al teléfono (USB, Bluetooth, email, etc.)
2. En el teléfono, ir a Ajustes → Seguridad → Permitir fuentes desconocidas
3. Abrir el archivo APK
4. Instalar

---

## Estructura de proyectos Android

### ClienteTCP

| Archivo | Descripción |
|---|---|
| `Api.kt` | Cliente Retrofit + modelos de datos |
| `MainActivity.kt` | Pantalla principal (estado, documentos, notificaciones) |
| `RegistroActivity.kt` | Formulario de registro |
| `SolicitarActivity.kt` | Formulario de solicitud de documento |

**Paquete:** `com.tcpfacturador.cliente`

### AdminTCP

| Archivo | Descripción |
|---|---|
| `Api.kt` | Cliente Retrofit + modelos de datos (24 endpoints) |
| `LoginActivity.kt` | Login del administrador |
| `MainActivity.kt` | Contenedor con BottomNavigation (5 fragments) |
| `SolicitudesFragment.kt` | Solicitudes pendientes + generar/anular |
| `TcpFragment.kt` | Gestión de TCPs (CRUD + activar + suspender) |
| `ClientesFragment.kt` | Gestión de clientes finales (CRUD) |
| `DocumentosFragment.kt` | Lista de documentos + filtro + PDF |
| `MasFragment.kt` | Configuración + recargas + password |

**Paquete:** `com.tcpfacturador.admin`

---

## Dependencias comunes

| Librería | Versión | Uso |
|---|---|---|
| Retrofit | 2.9.0 | Cliente HTTP |
| OkHttp | 4.12.0 | Motor HTTP + logging |
| Gson (converter) | — | Serialización JSON |
| Kotlinx Coroutines | 1.7.3 | Operaciones async |
| Material Design | 1.11.0 | Componentes UI |
| AndroidX Core KTX | 1.12.0 | Extensiones Android |

---

## Solución de problemas

### "JAVA_HOME not set"

```bash
# Windows
set JAVA_HOME=C:\Users\Asiel\jdk-23.0.2
set PATH=%JAVA_HOME%\bin;%PATH%

# Linux/Mac
export JAVA_HOME=/path/to/jdk
export PATH=$JAVA_HOME/bin:$PATH
```

### "SDK not found"

Verificar que `ANDROID_HOME` apunta al directorio correcto del SDK.

### "Could not resolve plugin"

Ejecutar:
```bash
.\gradlew.bat --refresh-dependencies
```

### Build falla con JDK incompatible

El proyecto usa `JavaVersion.VERSION_17`. JDK 17, 21 y 23 funcionan. Si se usa JDK 8 o 11, fallará.
