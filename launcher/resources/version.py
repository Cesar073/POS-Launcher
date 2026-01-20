"""
Sistema de versionado para la aplicación POS.

Este módulo centraliza la información de versión y metadata
de la aplicación. Es usado por:
- El launcher para verificar actualizaciones
- La UI para mostrar "Acerca de"
- El sistema de releases

Versionado Semántico (SemVer):
    MAJOR.MINOR.PATCH
    - MAJOR: Cambios incompatibles con versiones anteriores
    - MINOR: Nueva funcionalidad compatible
    - PATCH: Corrección de bugs

Uso:
    from pos_core.core.resources.version import (
        get_version,
        is_newer_version,
        get_app_info,
    )
    
    print(f"Version: {get_version()}")
    
    if is_newer_version("0.2.0"):
        print("Hay una actualizacion disponible!")
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

from resources.config import get_launcher_dir


# ============================================================================
# INFORMACIÓN DE LA APLICACIÓN
# ============================================================================

__version__ = "0.1.2"

# Notas de release (changelog) para esta versión
# Este texto aparecerá en el release de GitHub
"""
EJEMPLO PARA USAR EN CHANGELOG:
## Cambios en v0.1.3

### Nuevas características
- Mejoras en el sistema de actualización
- Nueva interfaz de usuario

### Correcciones
- Corrección de bugs menores
- Optimizaciones de rendimiento

### Notas
- Actualización recomendada para todos los usuarios
"""
__changelog__ = """
## Cambios en v0.1.3

### Nuevas características
- Se agrega copyright al launcher
"""

APP_NAME = "POS"
APP_FULL_NAME = "Launcher del Sistema de Punto de Venta"
APP_DESCRIPTION = "Software de gestion para puntos de venta"
APP_AUTHOR = ""
APP_WEBSITE = ""
APP_SUPPORT_EMAIL = ""

# Año de inicio del proyecto (para copyright)
APP_COPYRIGHT_YEAR_START = 2026


# ============================================================================
# FUNCIONES DE VERSIÓN
# ============================================================================

def get_version() -> str:
    """
    Retorna la versión actual de la aplicación.
    
    Returns:
        String de versión (ej: "0.1.0")
    """
    return __version__


def get_version_tuple() -> Tuple[int, int, int]:
    """
    Retorna la versión como tupla de enteros.
    
    Útil para comparaciones numéricas.
    
    Returns:
        Tupla (major, minor, patch)
    
    Example:
        >>> get_version_tuple()
        (0, 1, 0)
    """
    parts = __version__.split(".")
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """
    Convierte string de versión a tupla.
    
    Acepta formatos:
        - "1.2.3"
        - "v1.2.3" (con prefijo v)
    
    Args:
        version_str: String de versión
    
    Returns:
        Tupla (major, minor, patch)
    
    Raises:
        ValueError: Si el formato es inválido
    """
    # Remover 'v' inicial si existe (ej: "v1.0.0" -> "1.0.0")
    if version_str.startswith('v') or version_str.startswith('V'):
        version_str = version_str[1:]
    
    parts = version_str.split(".")
    if len(parts) != 3:
        raise ValueError(f"Formato de version invalido: {version_str}")
    
    return (int(parts[0]), int(parts[1]), int(parts[2]))


def compare_versions(v1: str, v2: str) -> int:
    """
    Compara dos versiones.
    
    Args:
        v1: Primera versión
        v2: Segunda versión
    
    Returns:
        -1 si v1 < v2
         0 si v1 == v2
         1 si v1 > v2
    
    Example:
        >>> compare_versions("1.0.0", "1.1.0")
        -1
        >>> compare_versions("2.0.0", "1.9.9")
        1
    """
    t1 = parse_version(v1)
    t2 = parse_version(v2)
    
    if t1 < t2:
        return -1
    elif t1 > t2:
        return 1
    return 0


def is_newer_version(other_version: str) -> bool:
    """
    Verifica si other_version es más nueva que la versión actual.
    
    Args:
        other_version: Versión a comparar
    
    Returns:
        True si other_version > __version__
    
    Example:
        >>> # Si __version__ = "0.1.0"
        >>> is_newer_version("0.2.0")
        True
        >>> is_newer_version("0.0.9")
        False
    """
    return compare_versions(other_version, __version__) > 0


def is_development_version() -> bool:
    """
    Verifica si la versión actual es de desarrollo (0.x.x).
    
    Por convención, versiones 0.x.x indican que el software
    está en desarrollo y puede tener cambios significativos.
    
    Returns:
        True si MAJOR == 0
    """
    return get_version_tuple()[0] == 0


# ============================================================================
# INFORMACIÓN DE LA APLICACIÓN
# ============================================================================

def get_app_info() -> Dict[str, Any]:
    """
    Retorna información completa de la aplicación.
    
    Útil para ventana "Acerca de" y metadata.
    
    Returns:
        Diccionario con toda la información de la app
    """
    current_year = datetime.now().year
    
    # Formato del copyright
    if current_year == APP_COPYRIGHT_YEAR_START:
        copyright_years = str(APP_COPYRIGHT_YEAR_START)
    else:
        copyright_years = f"{APP_COPYRIGHT_YEAR_START}-{current_year}"
    
    return {
        "version": __version__,
        "name": APP_NAME,
        "full_name": APP_FULL_NAME,
        "description": APP_DESCRIPTION,
        "author": APP_AUTHOR,
        "website": APP_WEBSITE,
        "support_email": APP_SUPPORT_EMAIL,
        "copyright": f"Copyright {copyright_years} {APP_AUTHOR}" if APP_AUTHOR else f"Copyright {copyright_years}",
        "is_development": is_development_version(),
    }


def get_copyright_text() -> str:
    """
    Retorna el texto de copyright formateado.
    
    Returns:
        Texto de copyright
    """
    info = get_app_info()
    return info["copyright"]


# ============================================================================
# GESTIÓN DE VERSION.JSON (para el launcher)
# ============================================================================

def get_launcher_version_info() -> Optional[Dict[str, Any]]:
    """
    Lee toda la información de launcher/version.json.
    
    Returns:
        Diccionario con la info o None si no existe
    """
    version_file = get_launcher_dir() / "version.json"
    
    if not version_file.exists():
        return None
    
    try:
        with open(version_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def get_installed_version() -> Optional[str]:
    """
    Lee la versión instalada desde launcher/version.json.
    
    Este archivo es usado por el launcher para saber qué
    versión está instalada sin ejecutar la app principal.
    
    Returns:
        Versión instalada o None si no existe el archivo
    """
    data = get_launcher_version_info()
    return data.get("version") if data else None


def update_last_check() -> None:
    """
    Actualiza la fecha de última verificación de actualizaciones.
    
    Llamar después de verificar si hay actualizaciones disponibles.
    """
    data = get_launcher_version_info()
    if not data:
        return
    data["last_update_check"] = datetime.now().isoformat()
    with open(get_launcher_dir() / "version.json", 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def needs_version_file_update() -> bool:
    """
    Verifica si version.json necesita actualizarse.
    
    Retorna True si:
    - No existe version.json
    - La versión en version.json es diferente a __version__
    
    Returns:
        True si debe actualizarse version.json
    """
    installed = get_installed_version()
    return installed != __version__

