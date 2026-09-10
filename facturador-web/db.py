"""Capa de base de datos: SQLite (local) o MySQL (Wasmer Edge con DB_*).
En Wasmer Edge las variables DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD
vienen pre-llenadas cuando el proyecto usa base de datos.
"""
import os
import sqlite3
import time

USE_MYSQL = bool(os.environ.get("DB_HOST"))
SQLITE_PATH = os.environ.get("SQLITE_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db"))

_mysql_conn = None

SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS admin_users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tcp_clientes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo TEXT UNIQUE NOT NULL,
  nombre_apellidos TEXT NOT NULL,
  ci TEXT DEFAULT '',
  direccion TEXT DEFAULT '',
  telefono TEXT DEFAULT '',
  email TEXT DEFAULT '',
  cuenta_cup TEXT DEFAULT '',
  agencia TEXT DEFAULT '',
  codigo_barra TEXT DEFAULT '',
  nit TEXT DEFAULT '',
  cargo TEXT DEFAULT 'TCP',
  device_id TEXT DEFAULT '',
  device_info TEXT DEFAULT '',
  token TEXT UNIQUE NOT NULL,
  estado TEXT DEFAULT 'pendiente',
  docs_disponibles INTEGER DEFAULT 0,
  plan_inicio TEXT DEFAULT '',
  plan_fin TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  cuno_blob BLOB,
  firma_blob BLOB,
  cuno_filename TEXT DEFAULT '',
  firma_filename TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS clientes_finales (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tcp_id INTEGER NOT NULL,
  empresa TEXT NOT NULL,
  cuenta_cup TEXT DEFAULT '',
  cuenta_cuc TEXT DEFAULT '',
  agencia TEXT DEFAULT '',
  codigo TEXT DEFAULT '',
  nit TEXT DEFAULT '',
  telefono_whatsapp TEXT DEFAULT '',
  direccion TEXT DEFAULT '',
  notas TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documentos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  numero TEXT DEFAULT '',
  tipo TEXT NOT NULL,
  tcp_id INTEGER NOT NULL,
  cliente_final_id INTEGER DEFAULT 0,
  contrato_no TEXT DEFAULT '',
  fecha TEXT DEFAULT '',
  numero_blanco INTEGER DEFAULT 0,
  fecha_blanco INTEGER DEFAULT 0,
  items_json TEXT NOT NULL,
  total REAL DEFAULT 0,
  estado TEXT DEFAULT 'solicitado',
  snap_json TEXT DEFAULT '',
  pdf_blob BLOB,
  created_at TEXT NOT NULL,
  generated_at TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS recargas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tcp_id INTEGER NOT NULL,
  tipo TEXT NOT NULL,
  docs INTEGER NOT NULL,
  monto REAL NOT NULL,
  fecha TEXT NOT NULL,
  admin TEXT DEFAULT '',
  nota TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notificaciones (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  destino TEXT NOT NULL,
  titulo TEXT NOT NULL,
  mensaje TEXT NOT NULL,
  tipo TEXT DEFAULT 'info',
  leida INTEGER DEFAULT 0,
  created_at TEXT NOT NULL,
  extra TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS config (
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);
"""

SCHEMA_MYSQL = """
CREATE TABLE IF NOT EXISTS admin_users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(100) UNIQUE NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  created_at VARCHAR(32) NOT NULL
);
CREATE TABLE IF NOT EXISTS tcp_clientes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  codigo VARCHAR(32) UNIQUE NOT NULL,
  nombre_apellidos VARCHAR(255) NOT NULL,
  ci VARCHAR(32) DEFAULT '',
  direccion VARCHAR(500) DEFAULT '',
  telefono VARCHAR(64) DEFAULT '',
  email VARCHAR(128) DEFAULT '',
  cuenta_cup VARCHAR(64) DEFAULT '',
  agencia VARCHAR(255) DEFAULT '',
  codigo_barra VARCHAR(64) DEFAULT '',
  nit VARCHAR(64) DEFAULT '',
  cargo VARCHAR(32) DEFAULT 'TCP',
  device_id VARCHAR(255) DEFAULT '',
  device_info VARCHAR(500) DEFAULT '',
  token VARCHAR(128) UNIQUE NOT NULL,
  estado VARCHAR(32) DEFAULT 'pendiente',
  docs_disponibles INT DEFAULT 0,
  plan_inicio VARCHAR(32) DEFAULT '',
  plan_fin VARCHAR(32) DEFAULT '',
  created_at VARCHAR(32) NOT NULL,
  cuno_blob LONGBLOB,
  firma_blob LONGBLOB,
  cuno_filename VARCHAR(255) DEFAULT '',
  firma_filename VARCHAR(255) DEFAULT ''
);
CREATE TABLE IF NOT EXISTS clientes_finales (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tcp_id INT NOT NULL,
  empresa VARCHAR(255) NOT NULL,
  cuenta_cup VARCHAR(64) DEFAULT '',
  cuenta_cuc VARCHAR(64) DEFAULT '',
  agencia VARCHAR(255) DEFAULT '',
  codigo VARCHAR(64) DEFAULT '',
  nit VARCHAR(64) DEFAULT '',
  telefono_whatsapp VARCHAR(64) DEFAULT '',
  direccion VARCHAR(500) DEFAULT '',
  notas VARCHAR(500) DEFAULT '',
  created_at VARCHAR(32) NOT NULL,
  INDEX (tcp_id)
);
CREATE TABLE IF NOT EXISTS documentos (
  id INT AUTO_INCREMENT PRIMARY KEY,
  numero VARCHAR(32) DEFAULT '',
  tipo VARCHAR(16) NOT NULL,
  tcp_id INT NOT NULL,
  cliente_final_id INT DEFAULT 0,
  contrato_no VARCHAR(64) DEFAULT '',
  fecha VARCHAR(32) DEFAULT '',
  numero_blanco TINYINT DEFAULT 0,
  fecha_blanco TINYINT DEFAULT 0,
  items_json MEDIUMTEXT NOT NULL,
  total DOUBLE DEFAULT 0,
  estado VARCHAR(32) DEFAULT 'solicitado',
  snap_json MEDIUMTEXT DEFAULT '',
  pdf_blob LONGBLOB,
  created_at VARCHAR(32) NOT NULL,
  generated_at VARCHAR(32) DEFAULT '',
  INDEX (tcp_id)
);
CREATE TABLE IF NOT EXISTS recargas (
  id INT AUTO_INCREMENT PRIMARY KEY,
  tcp_id INT NOT NULL,
  tipo VARCHAR(32) NOT NULL,
  docs INT NOT NULL,
  monto DOUBLE NOT NULL,
  fecha VARCHAR(32) NOT NULL,
  admin VARCHAR(100) DEFAULT '',
  nota VARCHAR(500) DEFAULT '',
  INDEX (tcp_id)
);
CREATE TABLE IF NOT EXISTS notificaciones (
  id INT AUTO_INCREMENT PRIMARY KEY,
  destino VARCHAR(64) NOT NULL,
  titulo VARCHAR(255) NOT NULL,
  mensaje VARCHAR(2000) NOT NULL,
  tipo VARCHAR(32) DEFAULT 'info',
  leida TINYINT DEFAULT 0,
  created_at VARCHAR(32) NOT NULL,
  extra VARCHAR(2000) DEFAULT '',
  INDEX (destino)
);
CREATE TABLE IF NOT EXISTS config (
  clave VARCHAR(64) PRIMARY KEY,
  valor VARCHAR(500) NOT NULL
);
"""


def _mysql_connect():
    import pymysql
    return pymysql.connect(
        host=os.environ.get("DB_HOST"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USERNAME"),
        password=os.environ.get("DB_PASSWORD"),
        database=os.environ.get("DB_NAME"),
        charset="utf8mb4",
        autocommit=True,
    )


def _sqlite_connect():
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_conn():
    global _mysql_conn
    if USE_MYSQL:
        try:
            if _mysql_conn is None:
                _mysql_conn = _mysql_connect()
            else:
                _mysql_conn.ping(reconnect=True)
            return _mysql_conn
        except Exception:
            _mysql_conn = _mysql_connect()
            return _mysql_conn
    return _sqlite_connect()


def _adapt(sql):
    # sqlite usa ?, mysql usa %s
    if USE_MYSQL:
        return sql.replace("?", "%s")
    return sql


def fetchall(sql, params=()):
    if USE_MYSQL:
        import pymysql.cursors
        conn = get_conn()
        with conn.cursor(pymysql.cursors.DictCursor) as cur:
            cur.execute(_adapt(sql), params)
            return list(cur.fetchall())
    else:
        conn = get_conn()
        try:
            cur = conn.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()


def fetchone(sql, params=()):
    rows = fetchall(sql, params)
    return rows[0] if rows else None


def execute(sql, params=()):
    """INSERT/UPDATE/DELETE. Retorna lastrowid (insert) o rowcount."""
    if USE_MYSQL:
        conn = get_conn()
        with conn.cursor() as cur:
            cur.execute(_adapt(sql), params)
            return cur.lastrowid or cur.rowcount
    else:
        conn = get_conn()
        try:
            cur = conn.execute(sql, params)
            conn.commit()
            return cur.lastrowid if cur.lastrowid else cur.rowcount
        finally:
            conn.close()


def init_db():
    schema = SCHEMA_MYSQL if USE_MYSQL else SCHEMA_SQLITE
    if USE_MYSQL:
        conn = get_conn()
        with conn.cursor() as cur:
            for stmt in schema.split(";"):
                s = stmt.strip()
                if s:
                    cur.execute(s)
        defaults = {
            "precio_plan": "1000", "docs_plan": "100", "dias_plan": "30",
            "precio_extra": "500", "docs_extra": "50", "dias_gracia": "15",
            "autogenerar": "0", "nombre_sistema": "Facturador TCP",
        }
        with conn.cursor() as cur:
            for k, v in defaults.items():
                cur.execute("INSERT IGNORE INTO config (clave, valor) VALUES (%s, %s)", (k, v))
    else:
        conn = get_conn()
        try:
            conn.executescript(schema)
            defaults = {
                "precio_plan": "1000", "docs_plan": "100", "dias_plan": "30",
                "precio_extra": "500", "docs_extra": "50", "dias_gracia": "15",
                "autogenerar": "0", "nombre_sistema": "Facturador TCP",
            }
            for k, v in defaults.items():
                conn.execute("INSERT OR IGNORE INTO config (clave, valor) VALUES (?, ?)", (k, v))
            conn.commit()
        finally:
            conn.close()


def get_config(clave, default=""):
    r = fetchone("SELECT valor FROM config WHERE clave=?", (clave,))
    return r["valor"] if r else default


def set_config(clave, valor):
    if USE_MYSQL:
        execute("INSERT INTO config (clave, valor) VALUES (?, ?) ON DUPLICATE KEY UPDATE valor=VALUES(valor)", (clave, valor))
    else:
        execute("INSERT OR REPLACE INTO config (clave, valor) VALUES (?, ?)", (clave, valor))


def now_str():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
