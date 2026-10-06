"""
Utilidades para el Launcher.

Funciones auxiliares para:
- Cálculo y verificación de checksums SHA256
- Manejo de archivos y directorios
- Operaciones de proceso
"""

import hashlib
import ctypes
import ctypes.wintypes
import json
import os
import sys
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from resources.logging_method import log_function

from resources.config import (
    APP_EXECUTABLE_NAME,
    APP_EXECUTABLE,
    LAUNCHER_CONFIG_FILENAME,
)

# ============================================================================
# CHECKSUMS
# ============================================================================

def calculate_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """
    Calcula el hash SHA256 de un archivo.
    
    Args:
        file_path: Ruta al archivo
        chunk_size: Tamaño del buffer de lectura
    
    Returns:
        Hash SHA256 en hexadecimal (lowercase)
    
    Raises:
        FileNotFoundError: Si el archivo no existe
        IOError: Si hay error de lectura
    """
    sha256 = hashlib.sha256()
    
    with open(file_path, 'rb') as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            sha256.update(data)
    
    return sha256.hexdigest()


def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """
    Verifica que el checksum de un archivo coincida con el esperado.
    
    Args:
        file_path: Ruta al archivo a verificar
        expected_hash: Hash SHA256 esperado
    
    Returns:
        True si el checksum coincide, False si no
    """
    try:
        actual_hash = calculate_sha256(file_path)
        return actual_hash.lower() == expected_hash.lower()
    except (FileNotFoundError, IOError):
        return False


def parse_checksums_file(content: str) -> dict:
    """
    Parsea el contenido de un archivo checksums.txt.
    
    Formato esperado (compatible con sha256sum):
        <hash>  <filename>
        <hash>  <filename>
    
    Args:
        content: Contenido del archivo checksums.txt
    
    Returns:
        Diccionario {filename: hash}
    """
    checksums = {}
    
    for line in content.strip().split('\n'):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Formato: hash  filename (dos espacios)
        # o: hash *filename (asterisco para binarios)
        parts = line.split()
        if len(parts) >= 2:
            hash_value = parts[0]
            filename = parts[1].lstrip('*')  # Remover asterisco si existe
            checksums[filename] = hash_value
    
    return checksums


# ============================================================================
# MANEJO DE ARCHIVOS
# ============================================================================

@log_function
def get_pos_base_dir_windows() -> Path:
    r"""
    Devuelve la ruta base de la aplicación NexoPOS en el directorio de usuario.
    Ejemplo: C:\Users\<usuario>\AppData\Local\NexoPOS

    CSIDL_LOCAL_APPDATA = 0x001C
    Es una constante definida en la API de Windows y representa:
    C:\Users\<usuario>\AppData\Local\NexoPOS

    Returns:
        Path al directorio base de la aplicación NexoPOS
    """
    csidl_local_appdata = 0x001C
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(
        None,
        csidl_local_appdata,
        None,
        0,
        buf
    )
    return Path(buf.value) / "NexoPOS"


@log_function
def get_launcher_config_path() -> Path:
    """Ruta al archivo de config local del Launcher."""
    return get_pos_base_dir_windows() / LAUNCHER_CONFIG_FILENAME


def _read_launcher_config() -> dict:
    """Lee launcher_config.json. No registra el contenido (puede traer secretos)."""
    config_path = get_launcher_config_path()
    if not config_path.exists():
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_launcher_config(data: dict) -> None:
    config_path = get_launcher_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


@dataclass(frozen=True)
class LauncherCredentials:
    """Credenciales locales. El token de instalación tiene prioridad sobre el UUID legado."""

    installation_token: Optional[str] = None
    installation_id: Optional[str] = None
    customer_uuid: Optional[str] = None
    edition: Optional[str] = None
    valid_until: Optional[str] = None


def _clean(value) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def credentials_from_mapping(data: dict, env_uuid: Optional[str] = None) -> LauncherCredentials:
    """
    Arma la credencial en memoria.

    Si hay installation_token, el UUID (archivo o entorno) no se usa como Bearer.
    """
    token = _clean(data.get("installation_token"))
    file_uuid = _clean(data.get("customer_uuid"))
    legacy_uuid = None if token else (_clean(env_uuid) or file_uuid)
    return LauncherCredentials(
        installation_token=token,
        installation_id=_clean(data.get("installation_id")),
        customer_uuid=legacy_uuid,
        edition=_clean(data.get("edition")),
        valid_until=_clean(data.get("valid_until")),
    )


def load_launcher_credentials() -> LauncherCredentials:
    """
    Lee la credencial de instalación y, si no hay token, el UUID legado.

    El UUID de entorno POS_CUSTOMER_UUID solo aplica cuando todavía no hay token.
    """
    return credentials_from_mapping(
        _read_launcher_config(),
        os.getenv("POS_CUSTOMER_UUID", ""),
    )


def get_pos_customer_uuid() -> Optional[str]:
    """
    UUID legado de PosCustomer.

    Orden: variable de entorno POS_CUSTOMER_UUID, luego launcher_config.json.
    Si ya hay installation_token, no se usa como Bearer.
    """
    return load_launcher_credentials().customer_uuid


def save_installation_credentials(
    *,
    installation_token: str,
    installation_id: str,
    edition: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> None:
    """Guarda el token y el id de instalación. No persiste el código de activación."""
    data = _read_launcher_config()
    data["installation_token"] = installation_token
    data["installation_id"] = installation_id
    if edition:
        data["edition"] = edition
    if valid_until:
        data["valid_until"] = valid_until
    _write_launcher_config(data)


def remember_license_cache(
    *,
    edition: Optional[str] = None,
    valid_until: Optional[str] = None,
) -> None:
    """Actualiza edición y vigencia en caché local, sin tocar el token."""
    data = _read_launcher_config()
    changed = False
    if edition and data.get("edition") != edition:
        data["edition"] = edition
        changed = True
    if valid_until and data.get("valid_until") != valid_until:
        data["valid_until"] = valid_until
        changed = True
    if changed:
        _write_launcher_config(data)


def client_os() -> str:
    """Sistema que el servidor usa para elegir el artefacto. El cliente no elige el ZIP."""
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


def _windows_machine_guid() -> Optional[str]:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
    except OSError:
        return None
    return _clean(value)


def get_machine_id() -> str:
    """
    Identificador estable del equipo, hasheado.

    En Windows sale del MachineGuid. Si no está disponible, se persiste un id local.
    """
    raw = _windows_machine_guid()
    if raw:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    data = _read_launcher_config()
    fallback = _clean(data.get("machine_fallback_id"))
    if not fallback:
        fallback = str(uuid.uuid4())
        data["machine_fallback_id"] = fallback
        _write_launcher_config(data)
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


@log_function
def safe_delete(file_path: Path, max_retries: int = 3, retry_delay: float = 0.5) -> bool:
    """
    Elimina un archivo de forma segura, con reintentos.
    
    Windows a veces mantiene archivos bloqueados brevemente.
    Esta función reintenta la eliminación si falla.
    
    Args:
        file_path: Ruta al archivo a eliminar
        max_retries: Número máximo de intentos
        retry_delay: Segundos entre intentos
    
    Returns:
        True si se eliminó, False si falló
    """
    for attempt in range(max_retries):
        try:
            if file_path.exists():
                file_path.unlink()
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return False
        except Exception:
            return False
    return False


@log_function
def safe_rename(src: Path, dst: Path, max_retries: int = 3, retry_delay: float = 0.5) -> bool:
    """
    Renombra/mueve un archivo de forma segura, con reintentos.
    
    Args:
        src: Ruta origen
        dst: Ruta destino
        max_retries: Número máximo de intentos
        retry_delay: Segundos entre intentos
    
    Returns:
        True si se renombró, False si falló
    """
    for attempt in range(max_retries):
        try:
            if dst.exists():
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
            
            shutil.move(str(src), str(dst))
            return True
        except PermissionError:
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return False
        except Exception as e:
            print(f"utils.py: safe_rename: Exception: {e}")
            return False
    return False


@log_function
def ensure_dir(directory: Path) -> bool:
    """
    Crea un directorio si no existe.
    
    Args:
        directory: Ruta del directorio
    
    Returns:
        True si existe o se creó, False si falló
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        return True
    except Exception:
        return False


@log_function
def clean_temp_files(directory: Path, pattern: str = "*") -> int:
    """
    Limpia archivos temporales de un directorio.
    
    Args:
        directory: Directorio a limpiar
        pattern: Patrón glob de archivos a eliminar
    
    Returns:
        Número de archivos eliminados
    """
    count = 0
    if not directory.exists():
        return count
    
    for file_path in directory.glob(pattern):
        if file_path.is_file():
            if safe_delete(file_path):
                count += 1
    
    return count


# ============================================================================
# MANEJO DE PROCESOS
# ============================================================================

@log_function
def is_process_running(process_name: str) -> bool:
    """
    Verifica si un proceso está corriendo.
    
    Args:
        process_name: Nombre del proceso (ej: "POS.exe")
    
    Returns:
        True si está corriendo, False si no
    """
    if sys.platform == "win32":
        # Windows: usar tasklist
        try:
            output = subprocess.check_output(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}"],
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            ).decode('utf-8', errors='ignore')
            return process_name.lower() in output.lower()
        except subprocess.SubprocessError:
            return False
    else:
        # Linux/macOS: usar pgrep
        try:
            subprocess.check_output(["pgrep", "-x", process_name])
            return True
        except subprocess.SubprocessError:
            return False


@log_function
def kill_process(process_name: str) -> bool:
    """
    Termina un proceso por nombre.
    
    Args:
        process_name: Nombre del proceso a terminar
    
    Returns:
        True si se terminó o no estaba corriendo, False si falló
    """
    if not is_process_running(process_name):
        return True
    
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/IM", process_name, "/F"],
                capture_output=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            time.sleep(0.5)  # Esperar a que termine
            return not is_process_running(process_name)
        except subprocess.SubprocessError:
            return False
    else:
        try:
            subprocess.run(["pkill", "-x", process_name], capture_output=True)
            time.sleep(0.5)
            return not is_process_running(process_name)
        except subprocess.SubprocessError:
            return False


@log_function
def start_application(executable_path: Path, wait: bool = False) -> Optional[subprocess.Popen]:
    """
    Inicia una aplicación.
    
    Args:
        executable_path: Ruta al ejecutable
        wait: Si True, espera a que termine
    
    Returns:
        Objeto Popen si se inició (y wait=False), None si falló
    """
    if not executable_path.exists():
        print(f"start_application: El ejecutable no existe: {executable_path}")
        return None
    
    work_dir = executable_path.parent
    
    # --- DIAGNÓSTICO TEMPORAL: capturar salida de POS.exe ---
    # TODO: Quitar este diagnóstico temporal.
    # Lo uso para ver porqué la app no puede iniciar desde el launcher.
    try:
        diag = subprocess.run(
            [str(executable_path)],
            cwd=str(work_dir),
            capture_output=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        print(f"start_application [DIAG]: exit_code={diag.returncode}")
        if diag.stdout:
            print(f"start_application [DIAG] STDOUT:\n{diag.stdout.decode('utf-8', errors='replace')}")
        if diag.stderr:
            print(f"start_application [DIAG] STDERR:\n{diag.stderr.decode('utf-8', errors='replace')}")
    except subprocess.TimeoutExpired:
        print("start_application [DIAG]: POS.exe sigue corriendo tras 5s (esto es bueno, no crashea)")
    except Exception as e:
        print(f"start_application [DIAG]: Error en diagnóstico: {e}")
    # --- FIN DIAGNÓSTICO ---
    
    try:
        if sys.platform == "win32":
            process = subprocess.Popen(
                [str(executable_path)],
                cwd=str(work_dir),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True
            )
        else:
            process = subprocess.Popen(
                [str(executable_path)],
                cwd=str(work_dir),
                start_new_session=True,
                close_fds=True
            )
        
        print(f"start_application: Proceso iniciado PID={process.pid}")
        time.sleep(0.5)
        
        exit_code = process.poll()
        if exit_code is not None:
            print(f"start_application: El proceso terminó inmediatamente con código {exit_code}")
            return None
        
        print(f"start_application: Proceso corriendo correctamente (PID={process.pid})")
        
        if wait:
            process.wait()
            return None
        
        return process
    except Exception as e:
        print(f"start_application: Error al iniciar: {e}")
        return None


# ============================================================================
# BACKUPS
# ============================================================================


@log_function
def has_backups() -> bool:
    """
    Verifica si hay backups disponibles.
    Analiza la carpeta de backup para verificar si existe el POS.exe de la versión anterior.
    """
    pos_base_dir = get_pos_base_dir_windows()
    if not pos_base_dir.exists():
        return False
    
    backup_dir = pos_base_dir / "backup"
    if not backup_dir.exists():
        return False
    
    for file in backup_dir.iterdir():
        if file.is_file() and file.name.startswith(APP_EXECUTABLE_NAME) and file.name.endswith(APP_EXECUTABLE):
            return True
    return False


# ============================================================================
# VERSION INFO
# ============================================================================

@log_function
def get_file_version_info(executable_path: Path) -> Optional[str]:
    """
    Obtiene la versión de un ejecutable (solo Windows).
    
    Args:
        executable_path: Ruta al ejecutable
    
    Returns:
        String de versión o None si no se pudo obtener
    """
    if sys.platform != "win32" or not executable_path.exists():
        return None
    
    try:
        # Intentar usar pywin32 si está disponible
        import win32api
        info = win32api.GetFileVersionInfo(str(executable_path), "\\")
        ms = info['FileVersionMS']
        ls = info['FileVersionLS']
        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}"
    except ImportError:
        # pywin32 no disponible
        return None
    except Exception:
        return None


# ============================================================================
# DETECCIÓN DE ENTORNO
# ============================================================================

@log_function
def is_frozen() -> bool:
    """
    Detecta si el launcher está compilado.
    
    Returns:
        True si está compilado, False si es código fuente
    """
    # PyInstaller
    if getattr(sys, 'frozen', False):
        return True
    
    # Nuitka
    import __main__
    if getattr(__main__, '__compiled__', False):
        return True
    
    return False
