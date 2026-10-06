"""
Sistema de Actualización del POS.

Este módulo contiene la lógica para:
- Verificar actualizaciones disponibles desde el servidor web
- Descargar nuevas versiones
- Aplicar actualizaciones
- Manejar rollback si algo falla

El sistema usa la API de Efecto Dominó (`/pos/api/updates/...`).
La credencial es el token de instalación devuelto por `/pos/api/activate`.
Si todavía no hay token y el config tiene el UUID legado, se sigue enviando ese UUID.

Uso:
    from launcher.updater import Updater

    updater = Updater(current_version="0.1.0", installation_token="...")

    # Verificar si hay actualización
    update_info = updater.check_for_updates()
    if update_info:
        print(f"Nueva versión disponible: {update_info.version}")

        # Descargar
        updater.download_update()

        # Aplicar
        updater.apply_update()
"""
import json
import re
import shutil
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from resources.logging_method import log_simple_class_methods

from resources.config import (
    WEB_API_BASE,
    UPDATES_CHECK_PATH,
    UPDATES_DOWNLOAD_PATH,
    ACTIVATE_PATH,
    LICENSE_PATH,
    EVENTS_PATH,
    HTTP_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_CHUNK_SIZE,
    USER_AGENT_PREFIX,
    MAX_DOWNLOAD_RETRIES,
    RETRY_DELAY,
    APP_EXECUTABLE,
    POS_DATABASE_FILENAME,
    get_temp_download_dir,
)
from resources.utils import (
    verify_checksum,
    safe_delete,
    safe_rename,
    ensure_dir,
    is_process_running,
    kill_process,
    get_pos_base_dir_windows,
    load_launcher_credentials,
    save_installation_credentials,
    remember_license_cache,
    client_os,
    get_machine_id,
)
from resources.version import get_version as get_launcher_version


@dataclass
class UpdateInfo:
    """Información sobre una actualización disponible."""
    id: int
    name: str
    version: str
    download_url: str
    changelog: str
    release_date: str = ""
    file_size: int = 0
    checksum: Optional[str] = None  # Formato: "sha256:hash"


class UpdateError(Exception):
    """Error durante el proceso de actualización."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        *,
        user_message: str | None = None,
        license_block: bool = False,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.user_message = user_message
        self.license_block = license_block


def is_connectivity_related_failure(exc: BaseException) -> bool:
    """
    Indica si el fallo parece de red / DNS / sin Internet (no un bug lógico de la app).
    """
    t = str(exc).lower()
    markers = (
        "getaddrinfo",
        "11001",  # Windows: host no encontrado / sin DNS
        "11002",
        "name or service not known",
        "network is unreachable",
        "no route to host",
        "error de conexión",
        "connection timed out",
        "timed out",
        "timeout:",
        "temporarily unavailable",
        "10060",  # Windows: timeout de conexión
        "10061",
        "[errno -2]",  # Linux: name resolution
        "[errno 101]",  # Network unreachable
    )
    return any(m in t for m in markers)


def user_message_for_failed_update_check(exc: UpdateError) -> str:
    """
    Texto para mostrar en pantalla cuando falla la verificación de actualizaciones.
    """
    custom = getattr(exc, "user_message", None)
    if custom:
        return custom
    code = getattr(exc, "status_code", None)
    if code == 401:
        return (
            "No se pudo identificar esta instalación.\n\n"
            "El identificador del cliente POS es inválido o falta. "
            "No se descargarán actualizaciones.\n\n"
            "Podés continuar con la versión que ya tenés instalada."
        )
    if code == 403:
        return (
            "La cuenta de este cliente POS está inactiva.\n\n"
            "No se descargarán actualizaciones. "
            "Podés continuar con la versión instalada."
        )
    if code == 404:
        return (
            "No hay una actualización disponible en el servidor.\n\n"
            "Podés continuar con la versión instalada."
        )
    if is_connectivity_related_failure(exc):
        return (
            "No se pudo comprobar si hay actualizaciones.\n\n"
            "Comprueba tu conexión a Internet y que el firewall o el antivirus no bloqueen "
            "esta aplicación. Suele ocurrir cuando no hay red, falla el DNS o no se puede "
            "alcanzar el servidor de actualizaciones.\n\n"
            "No es un fallo del programa: puedes reintentar la búsqueda o continuar con la "
            "versión que ya tienes instalada."
        )
    return (
        "No se pudo verificar si hay actualizaciones.\n\n"
        f"Detalle: {exc}\n\n"
        "Puedes reintentar más tarde o continuar con la versión instalada."
    )


def user_message_for_activation(exc: UpdateError) -> str:
    """Texto para un canje de código fallido. No incluye el código."""
    code = getattr(exc, "status_code", None)
    if code in (400, 401, 404):
        return (
            "El código no es válido, está vencido o fue revocado.\n\n"
            "Podés reintentar o continuar con la versión instalada."
        )
    if code == 409:
        return (
            "Este código ya fue utilizado.\n\n"
            "Si necesitás otra instalación, pedí un código nuevo."
        )
    if code == 403:
        detail = getattr(exc, "user_message", None) or str(exc)
        return (
            f"{detail}\n\n"
            "Podés continuar con la versión instalada."
        )
    if is_connectivity_related_failure(exc):
        return (
            "No se pudo activar esta instalación.\n\n"
            "Comprueba tu conexión a Internet y que el firewall o el antivirus no bloqueen "
            "esta aplicación.\n\n"
            "Podés reintentar o continuar con la versión instalada."
        )
    return (
        "No se pudo activar la instalación.\n\n"
        "Podés reintentar más tarde o continuar con la versión instalada."
    )


def bearer_value(installation_token: str | None, customer_uuid: str | None) -> str | None:
    """Elige la credencial. Función de módulo para no registrar el secreto en el log de métodos."""
    return installation_token or customer_uuid


def extract_license_fields(payload: dict) -> dict:
    """
    Lee edición, vigencia y updates_allowed del check o de GET /license.

    Acepta los campos en la raíz o dentro de un objeto `license`.
    `updates_allowed` queda en None si el servidor no lo envió.
    """
    nested = payload.get("license")
    if not isinstance(nested, dict):
        nested = {}

    def pick(key: str):
        if key in payload and payload[key] is not None:
            return payload[key]
        return nested.get(key)

    updates_allowed = pick("updates_allowed")
    if not isinstance(updates_allowed, bool):
        updates_allowed = None

    edition = pick("edition")
    valid_until = pick("valid_until")
    message = pick("message")
    billing_status = pick("billing_status")
    return {
        "edition": str(edition).strip() if isinstance(edition, str) and edition.strip() else None,
        "valid_until": str(valid_until).strip() if valid_until not in (None, "") else None,
        "updates_allowed": updates_allowed,
        "message": message.strip() if isinstance(message, str) else "",
        "billing_status": billing_status.strip().lower() if isinstance(billing_status, str) else "",
    }


def apply_debt_update_block(fields: dict) -> dict:
    """En deuda no hay actualizaciones. La vigencia extra la resuelve el POS."""
    if fields.get("billing_status") == "past_due":
        fields["updates_allowed"] = False
    return fields


def merge_license_fields(fields: dict, extra: dict) -> dict:
    if fields["updates_allowed"] is None:
        fields["updates_allowed"] = extra["updates_allowed"]
    if not fields["edition"]:
        fields["edition"] = extra["edition"]
    if not fields["valid_until"]:
        fields["valid_until"] = extra["valid_until"]
    if not fields["message"]:
        fields["message"] = extra["message"]
    if not fields["billing_status"]:
        fields["billing_status"] = extra["billing_status"]
    return fields


def database_filenames() -> tuple[str, ...]:
    """sys_store.dat y los archivos que SQLite deja al lado si hay un journal abierto."""
    name = POS_DATABASE_FILENAME
    return (name, f"{name}-journal", f"{name}-wal", f"{name}-shm")


def copy_database_from_backup(app_dir: Path) -> None:
    """
    Copia sys_store.dat desde backup/POS hacia POS.

    El archivo del backup no se mueve ni se borra.
    """
    source_dir = app_dir / "backup" / "POS"
    if not source_dir.is_dir():
        return
    dest_dir = app_dir / "POS"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for name in database_filenames():
        source = source_dir / name
        if source.is_file():
            shutil.copy2(source, dest_dir / name)


def _filename_from_content_disposition(header: str | None, fallback: str) -> str:
    if not header:
        return fallback
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)"?', header, re.IGNORECASE)
    if not match:
        return fallback
    name = match.group(1).strip().strip('"')
    return name or fallback


@log_simple_class_methods
class Updater:
    """
    Gestor de actualizaciones.

    Maneja la verificación, descarga y aplicación de actualizaciones
    desde el servidor web de Efecto Dominó.
    """

    def __init__(
        self,
        current_version: str | None = None,
        customer_uuid: str | None = None,
        installation_token: str | None = None,
        installation_id: str | None = None,
    ):
        """
        Inicializa el updater.

        Args:
            current_version: Versión actual instalada o None si no se encuentra instalada.
            customer_uuid: UUID legado. Se usa solo si no hay installation_token.
            installation_token: Credencial devuelta por /pos/api/activate.
            installation_id: Id de instalación que viaja en X-Pos-Installation-Id.
        """
        self.current_version = current_version
        self.customer_uuid = (customer_uuid or "").strip() or None
        self.installation_token = (installation_token or "").strip() or None
        self.installation_id = (installation_id or "").strip() or None
        self.updates_allowed: bool | None = None
        self.temp_dir = get_temp_download_dir()
        self.downloaded_file: Optional[Path] = None
        self.update_info: Optional[UpdateInfo] = None

        # Callback para reportar progreso de descarga
        self.progress_callback: Optional[Callable[[int, int], None]] = None

    def reload_credentials(self) -> None:
        """Vuelve a leer launcher_config.json. El token pisa al UUID legado."""
        credentials = load_launcher_credentials()
        self.installation_token = credentials.installation_token
        self.installation_id = credentials.installation_id
        self.customer_uuid = credentials.customer_uuid

    def has_auth(self) -> bool:
        return bool(bearer_value(self.installation_token, self.customer_uuid))

    def set_progress_callback(self, callback: Callable[[int, int], None]) -> None:
        """
        Establece un callback para reportar progreso de descarga.

        Args:
            callback: Función que recibe (bytes_descargados, bytes_totales)
        """
        self.progress_callback = callback

    def _user_agent(self) -> str:
        return f"{USER_AGENT_PREFIX}/{get_launcher_version()}"

    def _headers(self, *, binary: bool = False) -> dict[str, str]:
        bearer = bearer_value(self.installation_token, self.customer_uuid)
        if not bearer:
            raise UpdateError(
                "Falta el identificador del cliente POS.",
                status_code=401,
            )
        headers = {
            "Authorization": f"Bearer {bearer}",
            "User-Agent": self._user_agent(),
            "Accept": "application/octet-stream" if binary else "application/json",
        }
        if self.installation_token and self.installation_id:
            headers["X-Pos-Installation-Id"] = self.installation_id
        return headers

    def _error_detail_from_http(self, error: urllib.error.HTTPError, fallback: str) -> str:
        try:
            body = error.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            detail = data.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()
        except Exception:
            pass
        return fallback

    def _make_json_request(
        self,
        url: str,
        timeout: int = HTTP_TIMEOUT,
        *,
        method: str = "GET",
        payload: dict | None = None,
        authenticated: bool = True,
    ) -> dict:
        """Realiza una petición HTTP JSON al servidor web."""
        if authenticated:
            headers = self._headers(binary=False)
        else:
            headers = {
                "User-Agent": self._user_agent(),
                "Accept": "application/json",
            }
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        context = ssl.create_default_context()

        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                raw = response.read()
                if not raw:
                    return {}
                parsed = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise UpdateError(
                    self._error_detail_from_http(e, "Identificación inválida."),
                    status_code=401,
                )
            if e.code == 403:
                raise UpdateError(
                    self._error_detail_from_http(e, "Cuenta inactiva."),
                    status_code=403,
                )
            if e.code == 400:
                raise UpdateError(
                    self._error_detail_from_http(e, "Solicitud inválida."),
                    status_code=400,
                )
            if e.code == 404:
                raise UpdateError("No se encontró el recurso.", status_code=404)
            if e.code == 409:
                raise UpdateError(
                    self._error_detail_from_http(e, "El código ya fue utilizado."),
                    status_code=409,
                )
            raise UpdateError(f"Error HTTP {e.code}: {e.reason}", status_code=e.code)
        except urllib.error.URLError as e:
            raise UpdateError(f"Error de conexión: {e.reason}")
        except TimeoutError:
            raise UpdateError("Timeout: El servidor no respondió a tiempo")
        except json.JSONDecodeError:
            raise UpdateError("La respuesta del servidor tiene formato inválido")

        if not isinstance(parsed, dict):
            raise UpdateError("La respuesta del servidor tiene formato inválido")
        return parsed

    def activate(self, code: str) -> None:
        """
        Canjea un código de venta y guarda el token de instalación.

        El código no se escribe en el config ni se incluye en los errores.
        """
        normalized = (code or "").strip()
        if not normalized:
            raise UpdateError("Falta el código de activación.", status_code=400)

        url = f"{WEB_API_BASE.rstrip('/')}{ACTIVATE_PATH}"
        payload = {
            "code": normalized,
            "machine_id": get_machine_id(),
            "os": client_os(),
            "launcher_version": get_launcher_version(),
        }
        try:
            data = self._make_json_request(
                url,
                method="POST",
                payload=payload,
                authenticated=False,
            )
        except UpdateError as exc:
            message = str(exc).replace(normalized, "***")
            user_message = exc.user_message.replace(normalized, "***") if exc.user_message else None
            if exc.status_code == 403 and not user_message:
                user_message = message
            raise UpdateError(
                message,
                status_code=exc.status_code,
                user_message=user_message,
                license_block=exc.license_block,
            ) from None

        token = str(data.get("installation_token") or "").strip()
        installation_id = str(data.get("installation_id") or "").strip()
        if not token or not installation_id:
            raise UpdateError("El servidor no devolvió la credencial de instalación.")

        edition = data.get("edition")
        valid_until = data.get("valid_until")
        edition_text = str(edition).strip() if isinstance(edition, str) and edition.strip() else None
        valid_text = str(valid_until).strip() if valid_until not in (None, "") else None
        save_installation_credentials(
            installation_token=token,
            installation_id=installation_id,
            edition=edition_text,
            valid_until=valid_text,
        )
        self.installation_token = token
        self.installation_id = installation_id
        self.customer_uuid = None

    def _report_update_check_event(self) -> None:
        """Avisa al servidor que se consultaron actualizaciones. No corta el flujo si falla."""
        if not bearer_value(self.installation_token, self.customer_uuid):
            return
        url = f"{WEB_API_BASE.rstrip('/')}{EVENTS_PATH}"
        try:
            self._make_json_request(
                url,
                method="POST",
                payload={
                    "event": "update_check",
                    "app_version": self.current_version or "",
                    "os": client_os(),
                },
            )
        except UpdateError:
            return

    def _resolve_license(self, release_data: dict) -> dict:
        fields = extract_license_fields(release_data)
        if self._needs_license_lookup(fields):
            fields = self._lookup_license(fields)
        return apply_debt_update_block(fields)

    def _needs_license_lookup(self, fields: dict) -> bool:
        if not self.installation_token:
            return False
        if fields["updates_allowed"] is None:
            return True
        return not fields["billing_status"]

    def _lookup_license(self, fields: dict) -> dict:
        url = f"{WEB_API_BASE.rstrip('/')}{LICENSE_PATH}"
        try:
            payload = self._make_json_request(url)
        except UpdateError:
            return fields
        return merge_license_fields(fields, extract_license_fields(payload))

    def _raise_if_updates_blocked(self, fields: dict) -> None:
        self.updates_allowed = fields["updates_allowed"]
        if fields["updates_allowed"] is not False:
            return
        message = fields["message"] or "Las actualizaciones no están habilitadas para esta instalación."
        lines = [message]
        if fields["valid_until"] and fields["valid_until"] not in message:
            lines.append(f"Vigencia: {fields['valid_until']}")
        lines.append("Podés continuar con la versión que ya tenés instalada.")
        text = "\n\n".join(lines)
        raise UpdateError(text, user_message=text, license_block=True)

    def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        Verifica si hay una actualización disponible.
        Usa el ZIP que indica el servidor para la edición y el sistema autorizados.
        """
        if not bearer_value(self.installation_token, self.customer_uuid):
            raise UpdateError(
                "Falta el identificador del cliente POS.",
                status_code=401,
            )

        query = {"os": client_os()}
        if self.current_version:
            query["version"] = self.current_version.lstrip("vV")
        url = (
            f"{WEB_API_BASE.rstrip('/')}{UPDATES_CHECK_PATH}"
            f"?{urllib.parse.urlencode(query)}"
        )

        release_data = self._make_json_request(url)
        self._report_update_check_event()

        fields = self._resolve_license(release_data)
        try:
            remember_license_cache(
                edition=fields["edition"],
                valid_until=fields["valid_until"],
            )
        except Exception:
            pass
        self._raise_if_updates_blocked(fields)

        if not release_data.get("update_available"):
            return None

        available_version = str(release_data.get("version") or "").lstrip("vV")
        if not available_version:
            raise UpdateError("El servidor no envió la versión de la actualización")

        download_url = str(release_data.get("download_url") or "").strip()
        if not download_url:
            download_url = (
                f"{WEB_API_BASE.rstrip('/')}"
                f"{UPDATES_DOWNLOAD_PATH.format(version=available_version)}"
            )

        changelog = release_data.get("changelog") or "Sin descripción disponible"
        release_date = release_data.get("release_date") or ""
        if release_date and "T" in str(release_date):
            try:
                dt = datetime.fromisoformat(str(release_date).replace("Z", "+00:00"))
                release_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass

        checksum = release_data.get("checksum") or None
        if isinstance(checksum, str):
            checksum = checksum.strip() or None

        self.update_info = UpdateInfo(
            id=0,
            name=f"POS-v{available_version}.zip",
            version=available_version,
            download_url=download_url,
            changelog=changelog,
            release_date=str(release_date),
            file_size=int(release_data.get("file_size") or 0),
            checksum=checksum,
        )
        return self.update_info

    def _is_newer_version(self, other_version: str) -> bool:
        """
        Compara si other_version es más nueva que current_version.
        """
        if self.current_version is None:
            return True

        try:
            current = self._parse_version(self.current_version)
            other = self._parse_version(other_version)
            return other > current
        except (ValueError, AttributeError):
            return False

    def _parse_version(self, version_str: str) -> tuple:
        """
        Convierte string de versión a tupla comparable.

        Args:
            version_str: Versión como "1.2.3"

        Returns:
            Tupla (major, minor, patch)

        Raises:
            ValueError: Si la versión no es válida
        """
        if not version_str:
            raise ValueError("Versión vacía")

        clean = version_str.strip().lstrip("vV")
        parts = clean.split(".")

        if len(parts) < 3:
            parts.extend(["0"] * (3 - len(parts)))

        return tuple(int(p) for p in parts[:3])

    def download_update(self, update_info: Optional[UpdateInfo] = None) -> Path:
        """
        Descarga la actualización.
        """
        if self.updates_allowed is False:
            raise UpdateError(
                "Las actualizaciones no están habilitadas para esta instalación.",
                license_block=True,
                user_message=(
                    "Las actualizaciones no están habilitadas para esta instalación.\n\n"
                    "Podés continuar con la versión que ya tenés instalada."
                ),
            )

        info = update_info or self.update_info
        if not info:
            raise UpdateError("No hay información de actualización disponible")

        ensure_dir(self.temp_dir)
        download_path = self.temp_dir / info.name

        last_error = None
        for attempt in range(MAX_DOWNLOAD_RETRIES):
            try:
                download_path, header_checksum = self._download_file(
                    info.download_url, download_path, info.file_size
                )
                checksum = info.checksum or header_checksum
                if checksum:
                    if not self._verify_checksum(download_path, checksum):
                        safe_delete(download_path)
                        raise UpdateError(
                            "Verificación de checksum fallida. El archivo puede estar corrupto."
                        )
                    info.checksum = checksum
                break
            except UpdateError as e:
                last_error = e
                if e.status_code in (401, 403, 404):
                    safe_delete(download_path)
                    raise
                if attempt < MAX_DOWNLOAD_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
        else:
            safe_delete(download_path)
            raise UpdateError(
                f"Descarga fallida después de {MAX_DOWNLOAD_RETRIES} intentos: {last_error}"
            )

        self.downloaded_file = download_path
        return download_path

    def _download_file(
        self, url: str, destination: Path, expected_size: int = 0
    ) -> tuple[Path, Optional[str]]:
        """
        Descarga un archivo ZIP desde el servidor web con reporte de progreso.

        Returns:
            (ruta final, checksum del header X-Checksum-SHA256 si existe)
        """
        headers = self._headers(binary=True)
        headers["Accept-Encoding"] = "identity"

        opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
        )
        request = urllib.request.Request(url, headers=headers)

        try:
            with opener.open(request, timeout=DOWNLOAD_TIMEOUT) as response:
                total_size = int(response.headers.get("content-length", expected_size) or 0)
                header_checksum = response.headers.get("X-Checksum-SHA256") or None
                filename = _filename_from_content_disposition(
                    response.headers.get("Content-Disposition"),
                    destination.name,
                )
                filename = Path(filename).name
                dest = destination
                if filename and filename != destination.name:
                    dest = destination.with_name(filename)
                    if self.update_info:
                        self.update_info.name = filename

                downloaded = 0
                with open(dest, "wb") as f:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if self.progress_callback:
                            self.progress_callback(downloaded, total_size)

                if header_checksum:
                    header_checksum = header_checksum.strip()
                    if header_checksum and not header_checksum.lower().startswith("sha256:"):
                        header_checksum = f"sha256:{header_checksum}"
                return dest, header_checksum or None

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise UpdateError(
                    self._error_detail_from_http(e, "Identificación inválida."),
                    status_code=401,
                )
            if e.code == 403:
                raise UpdateError(
                    self._error_detail_from_http(e, "Cuenta inactiva."),
                    status_code=403,
                )
            if e.code == 404:
                raise UpdateError("El archivo de actualización no se encontró.", status_code=404)
            raise UpdateError(
                f"Error HTTP {e.code} descargando el archivo: {e.reason}",
                status_code=e.code,
            )
        except urllib.error.URLError as e:
            raise UpdateError(f"Error de conexión: {e.reason}")
        except IOError as e:
            raise UpdateError(f"Error escribiendo archivo: {e}")

    def _verify_checksum(self, file_path: Path, checksum_str: str) -> bool:
        """
        Verifica el checksum del archivo descargado.

        Args:
            file_path: Ruta al archivo
            checksum_str: Checksum en formato "algoritmo:hash" (ej: "sha256:abc123")

        Returns:
            True si el checksum es válido
        """
        if not checksum_str or not checksum_str.strip():
            return True

        if ":" in checksum_str:
            algorithm, expected_hash = checksum_str.split(":", 1)
        else:
            algorithm = "sha256"
            expected_hash = checksum_str

        if algorithm.lower() != "sha256":
            return True

        return verify_checksum(file_path, expected_hash.strip())

    def apply_update(self) -> bool:
        """
        Aplica la actualización descargada.
        Las Excepciones que puedan ocurrir detienen el proceso y son atrapadas por la UI.

        Este método:
        1. Cierra la aplicación si está corriendo
        2. Carga los archivos descargados en la carpeta de la app
        3. Copia sys_store.dat desde backup/POS hacia la carpeta POS nueva
        4. Actualiza version.json
        """
        if not self.downloaded_file or not self.downloaded_file.exists():
            raise UpdateError("No hay archivo descargado para aplicar")

        if not self.update_info:
            raise UpdateError("No hay información de actualización")

        if is_process_running(APP_EXECUTABLE):
            if not kill_process(APP_EXECUTABLE):
                raise UpdateError(
                    f"No se pudo cerrar {APP_EXECUTABLE}. "
                    "Por favor ciérralo manualmente e intenta de nuevo."
                )

        app_dir = get_pos_base_dir_windows()
        if not app_dir.exists():
            app_dir.mkdir(parents=True, exist_ok=True)

        app_path = app_dir / self.update_info.name
        if not safe_rename(src=self.downloaded_file, dst=app_path):
            raise UpdateError("Error al intentar mover el archivo comprimido a la carpeta de la app")

        with zipfile.ZipFile(app_path, "r") as zip_ref:
            top_level_dirs = {name.split("/")[0] for name in zip_ref.namelist() if "/" in name}
            zip_ref.extractall(app_path.parent)

        safe_delete(app_path)

        if len(top_level_dirs) == 1:
            extracted_folder_name = top_level_dirs.pop()
        else:
            extracted_folder_name = app_path.stem

        extracted_folder = app_path.parent / extracted_folder_name
        new_app_path = app_path.parent / "POS"

        if extracted_folder.exists() and extracted_folder != new_app_path:
            if not safe_rename(src=extracted_folder, dst=new_app_path):
                raise UpdateError("Error al intentar mover la carpeta descomprimida a la carpeta de la app")
        elif not extracted_folder.exists() and not new_app_path.exists():
            raise UpdateError(
                f"No se encontró la carpeta extraída '{extracted_folder_name}' en {app_path.parent}"
            )

        if sys.platform == "win32":
            executable_path = new_app_path / "POS_Windows.exe"
        else:
            executable_path = new_app_path / APP_EXECUTABLE

        if not safe_rename(src=executable_path, dst=app_dir / "POS" / APP_EXECUTABLE):
            raise UpdateError("Error al intentar mover el archivo executable a la carpeta de la app")

        copy_database_from_backup(app_dir)
        self._update_version_file(app_dir)

    def _update_version_file(self, pos_base_dir: Path) -> None:
        """
        Actualiza el campo updated_at del archivo version.json.
        """
        if not self.update_info:
            return

        try:
            if sys.platform == "win32":
                version_file = pos_base_dir / "version.json"
            else:
                version_file = Path.home() / ".local" / "share" / "POS" / "version.json"

            now = datetime.now().isoformat()

            data = {
                "version": self.update_info.version,
                "app_name": "POS",
                "updated_at": now,
            }

            with open(version_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def cleanup(self) -> None:
        """
        Limpia archivos temporales de la descarga.
        """
        if self.downloaded_file and self.downloaded_file.exists():
            safe_delete(self.downloaded_file)

        if self.temp_dir.exists():
            try:
                self.temp_dir.rmdir()
            except OSError:
                pass

    def get_changelog(self) -> str:
        """
        Retorna el changelog de la actualización disponible.

        Returns:
            Texto del changelog o mensaje por defecto
        """
        if self.update_info:
            return self.update_info.changelog or "Sin descripción disponible"
        return "No hay información de actualización"
