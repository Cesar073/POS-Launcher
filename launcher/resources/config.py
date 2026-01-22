"""
Configuración del Launcher.

Este archivo centraliza todas las configuraciones necesarias
para el sistema de actualización y el launcher.
"""

import sys
import os
from pathlib import Path
import tempfile


# ============================================================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ============================================================================

# Nombre del ejecutable principal (sin extensión)
APP_EXECUTABLE_NAME = "POS"

# Nombre del archivo de checksum
CHECKSUM_FILENAME = "checksums.txt"

# Extensión del ejecutable según el SO
if sys.platform == "win32":
    APP_EXECUTABLE = f"{APP_EXECUTABLE_NAME}.exe"
    print(f"config.py: APP_EXECUTABLE: {APP_EXECUTABLE}")
else:
    APP_EXECUTABLE = APP_EXECUTABLE_NAME
    print(f"config.py: APP_EXECUTABLE: {APP_EXECUTABLE}")


# ============================================================================
# CONFIGURACIÓN DE GITHUB RELEASES
# ============================================================================

# Configuración del repositorio
GITHUB_OWNER = "Cesar073"
GITHUB_REPO = "POS-Releases"

# API de GitHub
GITHUB_API_BASE = "https://api.github.com"

# Token de autenticación de GitHub (Personal Access Token)
# Requerido para repositorios privados. Para repos públicos puede ser None.

# CÓMO OBTENER UN TOKEN:
# 1. Ve a GitHub > Settings > Developer settings > Personal access tokens > Tokens (classic)
# 2. Click en "Generate new token (classic)"
# 3. Dale un nombre descriptivo
# 4. Selecciona el scope "repo" (para repos privados) o "public_repo" (para repos públicos)
# 5. Copia el token generado
# 6. Configura la variable de entorno GITHUB_TOKEN en tu sistema

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Patrón para buscar el asset en los releases
# El sistema buscará assets que coincidan con este patrón o con el nombre del ejecutable
# Ejemplos de patrones posibles:
# - "POS.exe" (nombre exacto del ejecutable)
# - "POS-Windows" (prefijo del asset)
# - "POS" (nombre base)
ASSET_NAME_PATTERN = APP_EXECUTABLE_NAME + "-Windows" # Por defecto usa el nombre de la app


# ============================================================================
# CONFIGURACIÓN DE RUTAS
# ============================================================================

def get_launcher_dir() -> Path:
    """
    Retorna el directorio donde está el launcher.
    
    Returns:
        Path al directorio del launcher (compilado o desarrollo)
    """
    return Path(sys.executable).parent / "launcher" / "POS"


def get_app_executable_path() -> Path:
    """
    Retorna la ruta al ejecutable principal de la aplicación.
    
    En desarrollo, busca en dist/POS/
    En producción, busca en el mismo directorio que el launcher
    
    Returns:
        Path al ejecutable POS.exe
    """
    launcher_dir = get_launcher_dir()
    
    return launcher_dir / APP_EXECUTABLE


def get_app_compressed_path(file_name: str) -> Path:
    """
    Retorna la ruta al archivo comprimido de la aplicación.
    
    Returns:
        Path al archivo comprimido POS.zip
    """
    launcher_dir = get_launcher_dir()
    return launcher_dir / file_name


def get_temp_download_dir() -> Path:
    """
    Retorna el directorio temporal para descargas.
    
    Returns:
        Path al directorio temporal
    """
    return Path(tempfile.gettempdir()) / "POS_Updates"


# ============================================================================
# CONFIGURACIÓN DE RED
# ============================================================================

# Timeout para conexiones HTTP (segundos)
HTTP_TIMEOUT = 5

# Timeout para descarga de archivos grandes (segundos)
DOWNLOAD_TIMEOUT = 600  # 10 minutos

# Tamaño del buffer para descarga (bytes)
DOWNLOAD_CHUNK_SIZE = 32768  # 32 KB (mejor para Drive)

# User-Agent para las peticiones HTTP
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Número de reintentos para descargas fallidas
MAX_DOWNLOAD_RETRIES = 3

# Tiempo de espera entre reintentos (segundos)
RETRY_DELAY = 3


# ============================================================================
# CONFIGURACIÓN DE UI
# ============================================================================

# Tamaño de la ventana del launcher
WINDOW_WIDTH = 500
WINDOW_HEIGHT = 450

# Título de la ventana
WINDOW_TITLE = "Actualizador POS"

# Colores del tema
THEME_PRIMARY = "#1a73e8"      # Azul principal
THEME_SUCCESS = "#34a853"       # Verde éxito
THEME_ERROR = "#ea4335"         # Rojo error
THEME_WARNING = "#fbbc04"       # Amarillo advertencia

# Tiempo que muestra la splash screen (ms)
SPLASH_DURATION = 1500


# ============================================================================
# CONFIGURACIÓN DE COMPORTAMIENTO
# ============================================================================

# Si es True, permite omitir actualizaciones
ALLOW_SKIP_UPDATE = True

# Tiempo máximo para esperar a que cierre la app antes de actualizar (segundos)
APP_CLOSE_TIMEOUT = 30
