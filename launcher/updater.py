"""
Sistema de Actualización del POS.

Este módulo contiene la lógica para:
- Verificar actualizaciones disponibles desde GitHub Releases
- Descargar nuevas versiones
- Aplicar actualizaciones
- Manejar rollback si algo falla

El sistema usa la API de GitHub para obtener información del último release
y descargar el ejecutable desde los assets del release.

Uso:
    from launcher.updater import Updater
    
    updater = Updater(current_version="0.1.0")
    
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
import urllib.request
import urllib.error
import ssl
import sys
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from resources.logging_method import log_simple_class_methods

from resources.config import (
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_API_BASE,
    GITHUB_TOKEN,
    ASSET_NAME_PATTERN,
    HTTP_TIMEOUT,
    DOWNLOAD_TIMEOUT,
    DOWNLOAD_CHUNK_SIZE,
    USER_AGENT,
    MAX_DOWNLOAD_RETRIES,
    RETRY_DELAY,
    APP_EXECUTABLE,
    get_temp_download_dir,
    get_app_compressed_path,
)
from resources.utils import (
    verify_checksum,
    safe_delete,
    safe_rename,
    ensure_dir,
    is_process_running,
    kill_process,
)


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
    pass


@log_simple_class_methods
class Updater:
    """
    Gestor de actualizaciones.
    
    Maneja la verificación, descarga y aplicación de actualizaciones
    desde GitHub Releases.
    """
    
    def __init__(self, current_version: str | None = None):
        """
        Inicializa el updater.
        
        Args:
            current_version: Versión actual instalada o None si no se encuentra instalada.
        """
        self.current_version = current_version
        self.temp_dir = get_temp_download_dir()
        self.downloaded_file: Optional[Path] = None
        self.update_info: Optional[UpdateInfo] = None
        
        # Callback para reportar progreso de descarga
        self.progress_callback: Optional[Callable[[int, int], None]] = None
    
    def set_progress_callback(self, callback: Callable[[int, int], None]) -> None:
        """
        Establece un callback para reportar progreso de descarga.
        
        Args:
            callback: Función que recibe (bytes_descargados, bytes_totales)
        """
        self.progress_callback = callback

    def _make_request(self, url: str, timeout: int = HTTP_TIMEOUT) -> bytes:
        """
        Realiza una petición HTTP GET a la API de GitHub.
        """
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/vnd.github+json",
        }
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        request = urllib.request.Request(url, headers=headers)
        context = ssl.create_default_context()
        
        try:
            with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
                response = response.read()
                return json.loads(response.decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise UpdateError(
                    "Error de autenticación. Verifica que el token de GitHub sea válido "
                    "y tenga permisos para acceder al repositorio."
                )
            elif e.code == 403:
                raise UpdateError(
                    "Acceso denegado. El token puede no tener permisos suficientes "
                    "o el repositorio requiere autenticación."
                )
            elif e.code == 404:
                raise UpdateError("No se encontró el repositorio o release")
            else:
                raise UpdateError(f"Error HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise UpdateError(f"Error de conexión: {e.reason}")
        except TimeoutError:
            raise UpdateError("Timeout: El servidor no respondió a tiempo")
    
    def check_for_updates(self) -> Optional[UpdateInfo]:
        """
        Verifica si hay una actualización disponible.
        Consulta la API de GitHub para obtener el último release
        y compara la versión disponible con la versión actual.
        """
        try:
            # Obtener el último release desde GitHub
            release_url = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
            release_data = self._make_request(release_url)
        except json.JSONDecodeError:
            raise UpdateError("La respuesta de GitHub tiene formato inválido")
        except UpdateError as e:
            print(f"Error saliendo por UpdateError: {e}")
            if "404" in str(e) or "No se encontró" in str(e):
                raise UpdateError("No se encontró ningún release en el repositorio")
            raise
        
        # Obtener versión del tag del release (puede tener 'v' al inicio)
        tag_name = release_data.get("tag_name", "")
        if not tag_name:
            raise UpdateError("El release no tiene tag_name")
        
        # Limpiar el tag para obtener la versión (remover 'v' si existe)
        available_version = tag_name.lstrip('vV')
        
        # Comparar versiones
        if not self._is_newer_version(available_version):
            return None
        
        # Buscar el asset que coincida con el ejecutable
        assets = release_data.get("assets", [])
        if not assets:
            raise UpdateError("El release no tiene assets disponibles")
        
        # Buscar el asset que coincida con el patrón o nombre del ejecutable
        asset = self._find_asset(assets)
        if not asset:
            raise UpdateError(
                f"No se encontró un asset compatible en el release. "
                f"Buscando: {ASSET_NAME_PATTERN} o {APP_EXECUTABLE}"
            )
        
        # Obtener URL de descarga del asset usando la API de GitHub
        # La API es más confiable que browser_download_url que puede requerir cookies/sesión
        asset_id = asset.get("id")
        if asset_id:
            # Usar la API de GitHub para descargar el asset directamente
            download_url = f"{GITHUB_API_BASE}/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/assets/{asset_id}"
        else:
            # Fallback a browser_download_url si no hay asset_id
            download_url = asset.get("browser_download_url", "")
            if not download_url:
                raise UpdateError("El asset no tiene URL de descarga ni asset_id")
        
        # Obtener información adicional del release
        changelog = release_data.get("body", "")
        if not changelog:
            changelog = "Sin descripción disponible"
        
        release_date = release_data.get("published_at", "")
        if release_date:
            # Formatear fecha (ISO 8601 a formato más legible)
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(release_date.replace('Z', '+00:00'))
                release_date = dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        
        file_size = asset.get("size", 0)
        
        # Crear objeto UpdateInfo
        self.update_info = UpdateInfo(
            id=asset_id,
            name=asset.get("name", ""),
            version=available_version,
            download_url=download_url,
            changelog=changelog,
            release_date=release_date,
            file_size=file_size,
            checksum=None,  # GitHub no proporciona checksum directamente en la API
        )
        
        return self.update_info
    
    def _find_asset(self, assets: list) -> Optional[dict]:
        """
        Busca el asset que coincida con el ejecutable.
        """
        # Patrones a buscar (en orden de prioridad)
        patterns = [
            f"{ASSET_NAME_PATTERN}.zip",  # Archivo ZIP
            f"{ASSET_NAME_PATTERN}.exe",  # Con extensión .exe
            APP_EXECUTABLE,  # Nombre exacto del ejecutable
            ASSET_NAME_PATTERN,  # Patrón configurado
        ]
        
        # También buscar assets que contengan el nombre
        for asset in assets:
            asset_name = asset.get("name", "")
            
            # Buscar coincidencia exacta primero
            for pattern in patterns:
                if asset_name == pattern:
                    return asset
            
            # Buscar si el nombre contiene el patrón
            for pattern in patterns:
                if pattern in asset_name:
                    return asset
        
        # Si no se encuentra, retornar el primer asset (fallback)
        if assets:
            return assets[0]
        
        return None
    
    def _is_newer_version(self, other_version: str) -> bool:
        """
        Compara si other_version es más nueva que current_version.
        """
        # Si no hay versión instalada, cualquier versión disponible es más nueva
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
        
        # Limpiar y parsear
        clean = version_str.strip().lstrip('vV')
        parts = clean.split('.')
        
        if len(parts) < 3:
            parts.extend(['0'] * (3 - len(parts)))
        
        return tuple(int(p) for p in parts[:3])
    
    def download_update(self, update_info: Optional[UpdateInfo] = None) -> Path:
        """
        Descarga la actualización.
        """
        info = update_info or self.update_info
        if not info:
            raise UpdateError("No hay información de actualización disponible")
        
        # Crear directorio temporal
        ensure_dir(self.temp_dir)
        
        # Nombre del archivo descargado
        download_path = self.temp_dir / info.name

        # Descargar con reintentos
        last_error = None
        for attempt in range(MAX_DOWNLOAD_RETRIES):
            try:
                self._download_file(info.download_url, download_path, info.file_size)
                break
            except UpdateError as e:
                last_error = e
                if attempt < MAX_DOWNLOAD_RETRIES - 1:
                    import time
                    time.sleep(RETRY_DELAY)
        else:
            raise UpdateError(f"Descarga fallida después de {MAX_DOWNLOAD_RETRIES} intentos: {last_error}")
        
        # Verificar checksum si está disponible
        if info.checksum:
            if not self._verify_checksum(download_path, info.checksum):
                safe_delete(download_path)
                raise UpdateError("Verificación de checksum fallida. El archivo puede estar corrupto.")
        
        self.downloaded_file = download_path
        return download_path

    def _download_file(self, url: str, destination: Path, expected_size: int = 0) -> None:
        """
        Descarga un archivo desde GitHub Releases con reporte de progreso.
        Usa la API de GitHub directamente para descargar assets.
        """

        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/octet-stream",
            "Accept-Encoding": "identity",
        }

        is_api_endpoint = "/releases/assets/" in url
        if is_api_endpoint:
            if not GITHUB_TOKEN:
                raise UpdateError(
                    "Se requiere un token de GitHub para descargar assets mediante la API. "
                    "Configura GITHUB_TOKEN en la configuración."
                )
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        
        if GITHUB_TOKEN:
            headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
        
        # Crear un opener que maneje redirecciones correctamente
        # La API de GitHub puede redirigir a un CDN, necesitamos seguir esas redirecciones
        opener = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler(),
            urllib.request.HTTPSHandler(context=ssl.create_default_context())
        )
        
        request = urllib.request.Request(url, headers=headers)
        
        try:
            # Usar el opener para seguir redirecciones automáticamente
            with opener.open(request, timeout=DOWNLOAD_TIMEOUT) as response:
                # Obtener tamaño total del archivo
                total_size = int(response.headers.get('content-length', expected_size))
                downloaded = 0
                
                with open(destination, 'wb') as f:
                    while True:
                        chunk = response.read(DOWNLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Reportar progreso
                        if self.progress_callback:
                            self.progress_callback(downloaded, total_size)
        
        except urllib.error.HTTPError as e:
            if hasattr(e, 'headers'):
                print(f"updater.py: _download_file: Headers respuesta: {dict(e.headers)}")
            
            error_msg = f"Error HTTP {e.code} descargando archivo desde GitHub"
            if e.code == 401:
                error_msg += ". Error de autenticación. Verifica que el token de GitHub sea válido."
            elif e.code == 403:
                error_msg += ". Acceso denegado. El token puede no tener permisos suficientes."
            elif e.code == 404:
                error_msg += ". El asset no se encontró. Verifica que el asset_id sea correcto y que el archivo exista en el release."
            else:
                error_msg += f": {e.reason}"
            raise UpdateError(error_msg)
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
        try:
            # Parsear formato "sha256:hash"
            if ':' in checksum_str:
                algorithm, expected_hash = checksum_str.split(':', 1)
            else:
                # Asumir SHA256 si no se especifica
                algorithm = 'sha256'
                expected_hash = checksum_str
            
            if algorithm.lower() != 'sha256':
                # Solo soportamos SHA256 por ahora
                return True
            else:
                return verify_checksum(file_path, expected_hash)
        except Exception as e:
            # Si hay error verificando, asumir que está bien
            return True

    def apply_update(self, backup: bool = True) -> bool:
        """
        Aplica la actualización descargada.
        
        Este método:
        1. Cierra la aplicación si está corriendo
        2. Hace backup del ejecutable actual (opcional)
        3. Reemplaza el ejecutable con el nuevo
        4. Actualiza version.json
        
        Args:
            backup: Si True, hace backup antes de reemplazar
        
        Returns:
            True si la actualización se aplicó correctamente
        
        Raises:
            UpdateError: Si la actualización falla
        """
        if not self.downloaded_file or not self.downloaded_file.exists():
            raise UpdateError("No hay archivo descargado para aplicar")
        
        if not self.update_info:
            raise UpdateError("No hay información de actualización")
        
        # Cerrar la aplicación si está corriendo

        if is_process_running(APP_EXECUTABLE):
            if not kill_process(APP_EXECUTABLE):
                raise UpdateError(
                    f"No se pudo cerrar {APP_EXECUTABLE}. "
                    "Por favor ciérralo manualmente e intenta de nuevo."
                )
        app_path = get_app_compressed_path(file_name=self.update_info.name)
        # Hacer backup
        backup_path = None
        if backup and app_path.exists():
            backup_path = app_path.with_suffix('.exe.bak')
            if not safe_rename(app_path, backup_path):
                raise UpdateError("No se pudo crear backup del ejecutable actual")
        # Aplicar actualización
        try:
            # Crear directorio de destino si no existe
            app_dir = app_path.parent
            if not app_dir.exists():
                app_dir.mkdir(parents=True, exist_ok=True)
            if not safe_rename(self.downloaded_file, app_path):
                # Restaurar backup si existe
                if backup_path and backup_path.exists():
                    safe_rename(backup_path, app_path)
                raise UpdateError("No se pudo instalar la nueva versión")
            # Lo que tenemos en app_path es un ZIP: necesitamos descomprimirlo en el mismo directorio que app_path
            import zipfile

            with zipfile.ZipFile(app_path, 'r') as zip_ref:
                zip_ref.extractall(app_path.parent)
            
            # Actualizar version.json local
            self._update_version_file()
            
            return True
        
        except Exception as e:
            # Intentar rollback
            if backup_path and backup_path.exists():
                safe_rename(backup_path, app_path)
            raise UpdateError(f"Error aplicando actualización: {e}")

    def _update_version_file(self) -> None:
        """
        Actualiza el archivo version.json con la nueva versión.
        """
        if not self.update_info:
            return
        
        try:
            # Intentar importar desde pos_core
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from pos_core.core.resources.paths import get_version_file_path, ensure_directories_exist
            
            ensure_directories_exist()
            version_file = get_version_file_path()
            
            from datetime import datetime
            
            # Leer datos existentes
            existing_data = {}
            if version_file.exists():
                try:
                    with open(version_file, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass
            
            # Actualizar con nueva versión
            now = datetime.now().isoformat()
            existing_data.update({
                "version": self.update_info.version,
                "app_name": "POS",
                "installed_at": existing_data.get("installed_at", now),
                "updated_at": now,
            })
            
            # Guardar
            version_file.parent.mkdir(parents=True, exist_ok=True)
            with open(version_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
        except ImportError:
            # Si no podemos importar pos_core, guardar en ubicación por defecto
            try:
                import os
                if sys.platform == "win32":
                    appdata = os.environ.get("APPDATA", "")
                    version_file = Path(appdata) / "POS" / "version.json"
                else:
                    version_file = Path.home() / ".local" / "share" / "POS" / "version.json"
                
                version_file.parent.mkdir(parents=True, exist_ok=True)
                
                from datetime import datetime
                now = datetime.now().isoformat()
                
                data = {
                    "version": self.update_info.version,
                    "app_name": "POS",
                    "updated_at": now,
                }
                
                with open(version_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception:
                pass  # Silenciar errores
    
    def cleanup(self) -> None:
        """
        Limpia archivos temporales de la descarga.
        """
        if self.downloaded_file and self.downloaded_file.exists():
            safe_delete(self.downloaded_file)
        
        # Limpiar directorio temporal si está vacío
        if self.temp_dir.exists():
            try:
                self.temp_dir.rmdir()
            except OSError:
                pass  # No está vacío, dejarlo
    
    def get_changelog(self) -> str:
        """
        Retorna el changelog de la actualización disponible.
        
        Returns:
            Texto del changelog o mensaje por defecto
        """
        if self.update_info:
            return self.update_info.changelog or "Sin descripción disponible"
        return "No hay información de actualización"
