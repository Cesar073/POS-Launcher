# Handoff POS-Launcher → servidor web (actualizaciones)

Documento para el agente que adapta **POS-Launcher**. Con este archivo alcanza: no hace falta el repo de la web.

Fecha del contrato: **2026-08-17**. Rama web: `feat/pos-modelos-fase1`.

---

## 1. Objetivo

El Launcher **deja de hablar con GitHub**. Consulta y descarga actualizaciones desde el servidor web de Efecto Dominó.

| Antes | Después |
|-------|---------|
| `GITHUB_*` + token de GitHub en el cliente | URL base de la web + UUID del cliente POS |
| `GET api.github.com/repos/.../releases/latest` | `GET /pos/api/updates/check` |
| Descarga del asset privado de GitHub | `GET /pos/api/updates/download/{version}` |
| Token GitHub en la PC del cliente | **Prohibido.** El token de GitHub queda solo en el servidor web |

Lo que **no cambia** en el Launcher: UI, backup local, aplicar ZIP, matar `POS.exe`, escribir `%LOCALAPPDATA%\NexoPOS\version.json`, rollback.

La descarga del instalador Inno **no entra en este handoff**.

---

## 2. Base URL

Producción:

```text
https://www.efectodomino.com.ar
```

Desarrollo local de la web (si hace falta apuntar el Launcher a un entorno de prueba):

```text
http://localhost:8000
```

o el puerto que use el stack (`8080` con Docker/Nginx).

El host **tiene que ser** uno de plataforma (`www.efectodomino.com.ar`, `efectodomino.com.ar`, `localhost`). No usar un dominio de tenant de Business Site.

Paths finales (el prefijo `/pos/` es obligatorio):

| Uso | Método | Path |
|-----|--------|------|
| ¿Hay update? | `GET` | `/pos/api/updates/check` |
| Descargar ZIP | `GET` | `/pos/api/updates/download/{version}` |

Config sugerida en `launcher/resources/config.py` (reemplaza el bloque GitHub):

```python
WEB_API_BASE = os.getenv("POS_WEB_API_BASE", "https://www.efectodomino.com.ar")
UPDATES_CHECK_PATH = "/pos/api/updates/check"
UPDATES_DOWNLOAD_PATH = "/pos/api/updates/download/{version}"  # fallback si no viene download_url
HTTP_TIMEOUT = 5
DOWNLOAD_TIMEOUT = 600
DOWNLOAD_CHUNK_SIZE = 32768
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY = 3
USER_AGENT = "POS-Launcher/{launcher_version}"  # ej. POS-Launcher/0.1.0
```

---

## 3. Autenticación (obligatoria)

Cada request de check y download **debe** autenticarse. Sin header válido el servidor responde **401** y no entrega el ZIP.

### 3.1. Token

El token es el **UUID de `PosCustomer`** (el negocio suscriptor), no el `id` numérico de la base.

- Formato: UUID v4, ejemplo `d0fe81b6-ac68-47ee-b624-3b4f602bb073`
- Lo genera el servidor al dar de alta el cliente (admin Django o comando `seed_pos_customer`)
- Se copia a mano al Launcher / config del cliente actual
- **No** es el token de GitHub
- **No** viaja en query string (queda en logs de proxy)

### 3.2. Headers obligatorios

```http
Authorization: Bearer <POS_CUSTOMER_UUID>
User-Agent: POS-Launcher/<version_del_launcher>
Accept: application/json
```

En la descarga del ZIP:

```http
Authorization: Bearer <POS_CUSTOMER_UUID>
User-Agent: POS-Launcher/<version_del_launcher>
Accept: application/octet-stream
```

### 3.3. Header opcional (recomendado)

Si el Launcher ya tiene (o puede generar y persistir) un UUID de instalación:

```http
X-Pos-Installation-Id: <POS_INSTALLATION_UUID>
```

- Debe pertenecer al mismo `PosCustomer` del Bearer
- Si viene mal formado o no existe → **400**
- Si no se envía, check y download igual funcionan
- Sirve para telemetría (`last_seen_at`, `installed_version`, log de descargas)

Fase 1: el cliente actual puede omitirlo. No bloquear actualizaciones por no tener instalación.

### 3.4. Dónde guardar el UUID en el cliente

Persistir en un archivo de config local del Launcher (junto a `version.json` o equivalente), **no** hardcodear en el binario.

Variable de entorno opcional para desarrollo: `POS_CUSTOMER_UUID`.

Si falta el UUID: mostrar mensaje (“falta identificar esta instalación”) y **continuar con la versión local**. No crashear.

### 3.5. CSRF / cookies

Los endpoints son `GET` JSON/binario. **No** hay sesión Django ni CSRF. No enviar cookies. No hace falta login web.

---

## 4. Check — ¿hay actualización?

### Request

```http
GET /pos/api/updates/check?version=0.2.1 HTTP/1.1
Host: www.efectodomino.com.ar
Authorization: Bearer d0fe81b6-ac68-47ee-b624-3b4f602bb073
User-Agent: POS-Launcher/0.1.0
Accept: application/json
```

Query:

| Param | Obligatorio | Descripción |
|-------|-------------|-------------|
| `version` | No, pero enviarlo siempre | Versión local leída de `version.json` (sin `v`, ej. `0.2.1`) |

Si no hay `version.json` / versión local: llamar **sin** query `version`. El servidor trata “sin versión” como “cualquier release publicado es más nuevo”.

Timeout: **5 s** (igual que hoy contra GitHub).

### Respuesta 200 — no hay update

```json
{
  "update_available": false,
  "current_latest": "0.2.1"
}
```

Si el servidor aún no cacheó ningún release publicado:

```json
{
  "update_available": false,
  "current_latest": ""
}
```

### Respuesta 200 — sí hay update

```json
{
  "update_available": true,
  "version": "0.3.0",
  "changelog": "- Mejoras y correcciones",
  "release_date": "2026-08-17",
  "file_size": 30050725,
  "download_url": "https://www.efectodomino.com.ar/pos/api/updates/download/0.3.0",
  "checksum": "sha256:948e8fbe520c7c5feb87e287ee4372af521cc1dcfe21c2ec6064f9b7a4422b35"
}
```

| Campo | Uso en el Launcher |
|-------|--------------------|
| `update_available` | Decidir si actualizar |
| `version` | Versión remota (ya sin `v`) |
| `changelog` | Mostrar al usuario |
| `release_date` | ISO `YYYY-MM-DD` o `null` |
| `file_size` | Progreso / validación |
| `download_url` | **Usar esta URL tal cual** (absoluta). No armarla a mano salvo fallback |
| `checksum` | `sha256:<hex>`. Verificar el ZIP descargado. Puede venir vacío |

### Comparación de versiones (igual que hoy)

El servidor ya compara. El Launcher **puede** confiar en `update_available`.

Si el Launcher revalida localmente, usar el mismo semver de 3 componentes:

```python
def parse_version(version_str: str) -> tuple[int, int, int]:
    clean = version_str.strip().lstrip("vV")
    parts = clean.split(".")
    if len(parts) < 3:
        parts.extend(["0"] * (3 - len(parts)))
    return tuple(int(p) for p in parts[:3])

def is_newer(remote: str, local: str | None) -> bool:
    if local is None:
        return True
    return parse_version(remote) > parse_version(local)
```

Regla: hay update si y solo si `remote > local` (major.minor.patch). Parseo inválido → tratar como “no hay update”.

---

## 5. Download — bajar el ZIP de la app POS

### Request

Preferido: `GET` a `download_url` del check (incluye host y path).

Fallback:

```http
GET /pos/api/updates/download/0.3.0 HTTP/1.1
Host: www.efectodomino.com.ar
Authorization: Bearer d0fe81b6-ac68-47ee-b624-3b4f602bb073
User-Agent: POS-Launcher/0.1.0
Accept: application/octet-stream
```

`{version}` es la versión **sin** prefijo `v` (ej. `0.3.0`).

- Timeout: **600 s**
- Chunks: 32 KB
- Reintentos: 3, con 3 s entre intentos
- Seguir redirecciones si las hubiera
- **Mismos headers de auth** que en el check (el `download_url` no incluye el token)

Este endpoint sirve el artefacto **POS app** (`POS-Windows-v{VERSION}.zip`), no el Launcher ni el instalador Inno.

### Respuesta 200

- Cuerpo: binario ZIP
- `Content-Length` si el servidor conoce el tamaño
- `X-Checksum-SHA256`: mismo valor que `checksum` del check (si está cargado)
- `Content-Disposition: attachment` con el nombre de archivo original (ej. `POS-Windows-v0.3.0.zip`)

Guardar a `%TEMP%\POS_Updates\` (o la ruta actual del Launcher) y seguir el flujo local existente (backup → aplicar ZIP → `version.json`).

### Verificar checksum

Si `checksum` o `X-Checksum-SHA256` viene con prefijo `sha256:`:

1. SHA-256 del archivo descargado
2. Comparar hex en minúsculas
3. Si no coincide: borrar el archivo, reintentar; si sigue mal, abortar update y seguir con la versión local

Si el checksum viene vacío: descargar igual (el servidor a veces cachea sin digest de GitHub).

---

## 6. Errores HTTP (contrato)

| Código | Causa | Qué hace el Launcher |
|--------|--------|----------------------|
| 200 | OK | Seguir el flujo |
| 400 | `X-Pos-Installation-Id` inválido | Ignorar instalación, reintentar **sin** ese header, o mensaje y seguir local |
| 401 | Falta `Authorization` o UUID desconocido | Mensaje: identificación inválida. **No** actualizar. Seguir con versión local |
| 403 | Cliente POS inactivo | Mensaje: cuenta inactiva. Seguir local |
| 404 | Versión no publicada / sin archivo | Mensaje: update no disponible. Seguir local |
| timeout / DNS | Servidor no respondió | Igual que hoy sin internet: seguir local |
| 5xx | Error del servidor | Reintentos de descarga; si fallan, seguir local |

Cuerpo de error (401/403/400):

```json
{ "detail": "Token inválido." }
```

**Nunca** mostrar ni loguear el Bearer token.

---

## 7. Flujo completo del Launcher (target)

```
1. Leer versión local → version.json
2. Leer POS_CUSTOMER_UUID de config local
3. Si no hay UUID → mensaje + seguir local (no llamar a la API)
4. GET {WEB_API_BASE}/pos/api/updates/check?version={local}
   Headers: Authorization Bearer, User-Agent
5. Si update_available == false → fin
6. GET download_url (mismos headers de auth)
7. Verificar SHA-256 si vino checksum
8. (Local, sin cambios) backup → aplicar ZIP → version.json → rollback opcional
9. Iniciar POS.exe
```

```mermaid
sequenceDiagram
    participant L as POS-Launcher
    participant WEB as efectodomino.com.ar

    L->>L: Leer version.json + UUID cliente
    L->>WEB: GET /pos/api/updates/check?version=...
    Note over L,WEB: Authorization: Bearer UUID
    WEB-->>L: update_available + download_url + checksum
    alt Hay actualización
        L->>WEB: GET download_url
        Note over L,WEB: Mismo Bearer
        WEB-->>L: ZIP + X-Checksum-SHA256
        L->>L: Verificar hash, backup, aplicar, version.json
    end
    L->>L: Iniciar POS.exe
```

---

## 8. Qué borrar / no portar

| Quitar del Launcher | Motivo |
|---------------------|--------|
| `GITHUB_OWNER`, `GITHUB_REPO`, `GITHUB_API_BASE` | Ya no consultás GitHub |
| `GITHUB_TOKEN` / `Authorization: Bearer ghp_...` | El token de GitHub **no debe existir** en el cliente |
| Parser de `tag_name` / lista de assets / `_find_asset` | Lo hace el servidor |
| Llamadas a `/releases/latest` y `/releases/assets/{id}` | Reemplazadas por check + download |

Conservar: `_parse_version` / `_is_newer_version` si los usás para UI; apply/backup/rollback; lectura de `version.json`.

---

## 9. Checklist para el agente del Launcher

- [ ] Reemplazar config GitHub por `WEB_API_BASE` + paths `/pos/api/updates/...`
- [ ] Persistir `POS_CUSTOMER_UUID` en config local (inyectable por env en dev)
- [ ] Enviar `Authorization: Bearer <uuid>` en **check y download**
- [ ] Enviar `User-Agent: POS-Launcher/<version>`
- [ ] Usar `download_url` de la respuesta de check
- [ ] Verificar `checksum` / `X-Checksum-SHA256` cuando no esté vacío
- [ ] Timeouts 5 s (check) y 600 s (download); 3 reintentos en download
- [ ] 401/403/timeout: no crashear; seguir con la versión instalada
- [ ] No incluir token de GitHub en el binario ni en logs
- [ ] No implementar descarga Inno en este cambio
- [ ] Opcional: `X-Pos-Installation-Id` cuando exista UUID de instalación

---

## 10. Ejemplo mínimo (capa de red)

Solo ilustrativo. Adaptar a `updater.py` existente (no copiar UI/apply).

```python
import urllib.request

def _headers(customer_uuid: str, launcher_version: str, *, binary: bool = False) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {customer_uuid}",
        "User-Agent": f"POS-Launcher/{launcher_version}",
        "Accept": "application/octet-stream" if binary else "application/json",
    }

def check_update(base: str, customer_uuid: str, local_version: str | None) -> dict:
    url = f"{base.rstrip('/')}/pos/api/updates/check"
    if local_version:
        url += f"?version={local_version}"
    req = urllib.request.Request(url, headers=_headers(customer_uuid, "0.1.0"))
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.load(resp)

def download_update(download_url: str, customer_uuid: str, dest_path: Path) -> None:
    req = urllib.request.Request(
        download_url,
        headers=_headers(customer_uuid, "0.1.0", binary=True),
    )
    with urllib.request.urlopen(req, timeout=600) as resp, dest_path.open("wb") as out:
        while True:
            chunk = resp.read(32768)
            if not chunk:
                break
            out.write(chunk)
```

---

## 11. Contacto / datos del cliente actual

El UUID del cliente de producción se copia desde el admin de la web (`Pos customers`) o de la salida de:

```bash
uv run python efecto_domino/manage.py seed_pos_customer --name "..."
```

El agente del Launcher **no** genera ese UUID: lo recibe como dato de configuración.

---

*Contrato implementado en la web: `pos.views.updates` + `pos.services.auth`. El servidor rechaza check/download sin Bearer válido.*
