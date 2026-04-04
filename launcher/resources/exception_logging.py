"""
Registro de excepciones en archivo para el launcher compilado (sin consola).

Escribe en %LocalAppData%\\NexoPOS\\launcher_errors.log (append, UTF-8).
"""

from __future__ import annotations

import logging
import sys
import traceback
from pathlib import Path
from typing import Optional

_logger: Optional[logging.Logger] = None


def get_log_file_path() -> Path:
    """Ruta del archivo de log junto a los datos de la app."""
    try:
        from resources.utils import get_pos_base_dir_windows

        base = get_pos_base_dir_windows()
    except Exception:
        base = Path.home() / "AppData" / "Local" / "NexoPOS"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base / "launcher_errors.log"


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
