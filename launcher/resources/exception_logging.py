"""
Registro de excepciones en archivo para el launcher compilado (sin consola).

Escribe en %LocalAppData%\\NexoPOS\\Launcher\\logs\\launcher_errors.log (append, UTF-8).
Al cerrar el launcher envía al servidor solo el tramo que todavía no se mandó.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import ssl
import sys
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

_logger: Optional[logging.Logger] = None
_LOG_FILENAME = "launcher_errors.log"
_POS_STARTUP_LOG_FILENAME = "pos_startup.log"
_OFFSET_FILENAME = ".launcher_errors.upload_offset"


def _nexo_pos_dir() -> Path:
    try:
        from resources.utils import get_pos_base_dir_windows

        return get_pos_base_dir_windows()
    except Exception:
        return Path.home() / "AppData" / "Local" / "NexoPOS"


def get_log_file_path() -> Path:
    """Ruta del archivo de log: NexoPOS/Launcher/logs/launcher_errors.log."""
    base = _nexo_pos_dir()
    log_dir = base / "Launcher" / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    new_path = log_dir / _LOG_FILENAME
    old_path = base / _LOG_FILENAME
    if old_path.is_file() and not new_path.exists():
        try:
            old_path.replace(new_path)
        except OSError:
            pass
    return new_path


def get_pos_startup_log_path() -> Path:
    """stdout/stderr del POS lanzado por el launcher: Launcher/logs/pos_startup.log."""
    return get_log_file_path().parent / _POS_STARTUP_LOG_FILENAME


def _ensure_logger() -> logging.Logger:
    global _logger
    if _logger is not None:
        return _logger
    log_path = get_log_file_path()
    lg = logging.getLogger("pos_launcher.errors")
    lg.setLevel(logging.DEBUG)
    lg.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8", delay=True)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    lg.addHandler(fh)
    lg.propagate = False
    _logger = lg
    return lg


def install_exception_logging() -> None:
    """
    Configura logging a archivo y engancha excepciones no capturadas del hilo principal.
    Debe llamarse al inicio de main().
    """
    log = _ensure_logger()
    try:
        log.info("--- Inicio de sesión launcher --- Python %s | ejecutable: %s", sys.version.split()[0], sys.executable)
    except Exception:
        pass

    def _excepthook(exc_type, exc_value, exc_tb):
        try:
            msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            log.critical("Excepción no capturada (sys.excepthook):\n%s", msg)
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    sys.excepthook = _excepthook


def log_exception(exc: BaseException, context: str = "") -> None:
    """Registra una excepción con traceback completo."""
    log = _ensure_logger()
    try:
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        if context:
            log.error("%s\n%s", context, tb)
        else:
            log.error("Excepción:\n%s", tb)
    except Exception:
        pass


def log_message(level: int, msg: str, *args) -> None:
    """Mensaje de diagnóstico (INFO/DEBUG) al mismo archivo."""
    try:
        _ensure_logger().log(level, msg, *args)
    except Exception:
        pass


def _offset_path() -> Path:
    return get_log_file_path().parent / _OFFSET_FILENAME


def _read_offset() -> int:
    try:
        raw = _offset_path().read_text(encoding="utf-8").strip()
        return max(0, int(raw))
    except (OSError, ValueError):
        return 0


def _write_offset(offset: int) -> None:
    _offset_path().write_text(str(offset), encoding="utf-8")


def _flush_log() -> None:
    log = _logger
    if log is None:
        return
    for handler in list(log.handlers):
        try:
            handler.flush()
        except Exception:
            pass


def _pending_log() -> tuple[str, int]:
    """Texto nuevo desde el último envío y el offset final del archivo."""
    _flush_log()
    path = get_log_file_path()
    try:
        data = path.read_bytes()
    except OSError:
        return "", 0
    offset = _read_offset()
    if offset > len(data):
        offset = 0
    chunk = data[offset:]
    if not chunk:
        return "", len(data)
    text = chunk.decode("utf-8", errors="replace")
    from resources.config import MAX_LOG_UPLOAD_CHARS

    if len(text) > MAX_LOG_UPLOAD_CHARS:
        text = text[-MAX_LOG_UPLOAD_CHARS:]
    return text, len(data)


def _current_user() -> str:
    return (os.environ.get("USERNAME") or os.environ.get("USER") or "").strip()


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(0.2)
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return ""


def _pos_version() -> str:
    path = _nexo_pos_dir() / "version.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    version = data.get("version")
    return str(version).strip() if version else ""


def _post_log(text: str) -> bool:
    from resources.config import LOG_UPLOAD_TIMEOUT, LOGS_PATH, WEB_API_BASE
    from resources.utils import load_launcher_credentials
    from resources.version import get_version
    from updater import bearer_value

    credentials = load_launcher_credentials()
    bearer = bearer_value(credentials.installation_token, credentials.customer_uuid)
    if not bearer:
        return False

    payload = {
        "usuario": _current_user(),
        "ip": _local_ip(),
        "pos_version": _pos_version(),
        "launcher_version": get_version(),
        "log": text,
    }
    headers = {
        "Authorization": f"Bearer {bearer}",
        "User-Agent": f"POS-Launcher/{get_version()}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if credentials.installation_token and credentials.installation_id:
        headers["X-Pos-Installation-Id"] = credentials.installation_id

    url = f"{WEB_API_BASE.rstrip('/')}{LOGS_PATH}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    context = ssl.create_default_context()
    try:
        with urllib.request.urlopen(request, timeout=LOG_UPLOAD_TIMEOUT, context=context) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def upload_error_log() -> None:
    """Envía el log nuevo. Si falla, no avanza el offset y se reintenta en el próximo cierre."""
    try:
        text, new_offset = _pending_log()
        if not text.strip():
            return
        if not _post_log(text):
            return
        _write_offset(new_offset)
    except Exception:
        return
