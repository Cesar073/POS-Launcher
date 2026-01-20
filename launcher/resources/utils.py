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
import sys
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional


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


def get_pos_base_dir_windows() -> Path:
    csidl_local_appdata = 0x001C
    buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
    ctypes.windll.shell32.SHGetFolderPathW(
        None,
        csidl_local_appdata,
        None,
        0,
        buf
    )
    return Path(buf.value) / "POS"


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
    print(f"utils.py: safe_rename: src: {src}, dst: {dst}")
    for attempt in range(max_retries):
        try:
            # Eliminar destino si existe
            if dst.exists():
                dst.unlink()
            
            # Mover archivo
            shutil.move(str(src), str(dst))
            return True
        except PermissionError:
            print(f"utils.py: safe_rename: PermissionError: {attempt}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                return False
        except Exception as e:
            print(f"utils.py: safe_rename: Exception: {e}")
            return False
    print(f"utils.py: safe_rename: False")
    return False


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
            print(f"utils.py: is_process_running: output: {output}")
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
        return None
    
    try:
        if sys.platform == "win32":
            # Windows: usar DETACHED_PROCESS para que no dependa del launcher
            process = subprocess.Popen(
                [str(executable_path)],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True
            )
        else:
            # Linux/macOS
            process = subprocess.Popen(
                [str(executable_path)],
                start_new_session=True,
                close_fds=True
            )
        
        if wait:
            process.wait()
            return None
        
        return process
    except Exception:
        return None


# ============================================================================
# VERSION INFO
# ============================================================================

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
