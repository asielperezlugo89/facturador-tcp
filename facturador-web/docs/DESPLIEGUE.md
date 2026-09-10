# Despliegue

## Despliegue local (desarrollo)

### Requisitos

- Python 3.10 o superior
- pip

### Pasos

```bash
cd facturador-web
pip install -r requirements.txt
python app.py
```

El servidor arranca en `http://127.0.0.1:5000`.

**Credenciales:** `admin` / `admin123`

La base de datos SQLite se crea automáticamente en `data.db`.

---

## Despliegue en Wasmer Edge

Wasmer Edge detecta automáticamente proyectos Python/Flask cuando encuentra `requirements.txt` + `app.py`.

### Requisitos

- Cuenta en [wasmer.io](https://wasmer.io)
- Dominio configurado en Wasmer
- Repositorio en GitHub

### Paso 1: Preparar el repositorio

```bash
cd "D:\ .PY_PROYECT\tcp-server"
git init
git add .
git commit -m "Initial commit"
```

Asegurarse de que `.gitignore` excluye `data.db`:
```
data.db
*.pyc
__pycache__/
prueba_*.pdf
.env
```

Subir a GitHub:
```bash
gh repo create facturador-tcp --public --source=. --push
```

### Paso 2: Crear la app en Wasmer

1. Ir a [wasmer.io/dashboard](https://wasmer.io/dashboard)
2. Click **"New App"**
3. Seleccionar **"From GitHub"**
4. Elegir el repositorio `facturador-tcp`
5. Wasmer detecta automáticamente Python/Flask

### Paso 3: Configurar variables de entorno

En el dashboard de Wasmer, ir a **Settings → Environment Variables**:

| Variable | Valor | Descripción |
|---|---|---|
| `SECRET_KEY` | Texto largo aleatorio | Clave secreta de Flask (obligatorio) |
| `DB_HOST` | (automático de Wasmer) | Host de MySQL (se llena automáticamente) |
| `DB_PORT` | (automático de Wasmer) | Puerto de MySQL |
| `DB_NAME` | (automático de Wasmer) | Nombre de la base de datos |
| `DB_USERNAME` | (automático de Wasmer) | Usuario de MySQL |
| `DB_PASSWORD` | (automático de Wasmer) | Contraseña de MySQL |

> Las variables `DB_*` se rellenan automáticamente cuando Wasmer adjunta una base de datos MySQL al proyecto.

### Paso 4: Configurar el comando de arranque

Si Wasmer lo solicita, usar:
```
gunicorn app:app --bind 0.0.0.0:$PORT --workers 2
```

### Paso 5: Desplegar

Click **"Deploy"**. La primera vez:
1. Wasmer instala las dependencias de `requirements.txt`
2. El servidor crea las tablas de la base de datos automáticamente
3. Se crea el usuario admin por defecto (`admin` / `admin123`)

### Paso 6: Verificar

Abrir `https://SU-DOMINIO/login` y hacer login con `admin` / `admin123`.

---

## Checklist post-despliegue

- [ ] Login exitoso con `admin` / `admin123`
- [ ] Cambiar contraseña en **Config**
- [ ] Copiar la URL base y el token admin API de Config
- [ ] Revisar precios, días y período de gracia
- [ ] Configurar modo `autogenerar` si se desea
- [ ] Probar ciclo completo: registrar TCP → activar → solicitar doc → generar → PDF
- [ ] Actualizar `SERVER_URL` en `android/ClienteTCP/gradle.properties`
- [ ] Actualizar `SERVER_URL` en `android/AdminTCP/gradle.properties`
- [ ] Compilar ambas APKs
- [ ] Instalar APKs en dispositivos de prueba

---

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `SECRET_KEY` | `tcp-facturador-secreto-local-2026` | Clave de sesiones Flask |
| `SQLITE_PATH` | `./data.db` | Ruta de SQLite (solo local) |
| `DB_HOST` | (none) | Si existe, usa MySQL en vez de SQLite |
| `DB_PORT` | `3306` | Puerto MySQL |
| `DB_NAME` | (none) | Nombre de la BD MySQL |
| `DB_USERNAME` | (none) | Usuario MySQL |
| `DB_PASSWORD` | (none) | Contraseña MySQL |

---

## Recuperación de contraseña admin

### Local

Borrar `data.db` y reiniciar el servidor. Se recrea con `admin` / `admin123` (se pierden todos los datos).

### Wasmer (producción)

```bash
python3 -c "
from werkzeug.security import generate_password_hash as g
import db
db.execute(
    'UPDATE admin_users SET password_hash=? WHERE username=?',
    (g('NUEVA_CLAVE'), 'admin')
)
print('ok')
"
```

Ejecutar en la consola de Wasmer o como comando de arranque temporal.
