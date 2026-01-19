#!/usr/bin/env python
"""
Script de compilación para el Launcher POS.

Compila el launcher con Nuitka como ejecutable standalone.
El launcher es un ejecutable separado que verifica actualizaciones
e inicia la aplicación principal (POS.exe).

Uso:
    python build/build_launcher.py          # Compilar
    python build/build_launcher.py --clean  # Limpiar y compilar

Requisitos:
    - Python 3.10+
    - Nuitka instalado
    - Visual Studio Build Tools (Windows)
"""

import subprocess
import sys
import shutil
import argparse
import time
from pathlib import Path


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Version del launcher
LAUNCHER_VERSION = "1.0.0"

# Raíz del proyecto
PROJECT_ROOT = Path(__file__).parent.parent

# Script principal del launcher
LAUNCHER_SCRIPT = PROJECT_ROOT / "launcher" / "main.py"

# Carpeta de salida
OUTPUT_DIR = PROJECT_ROOT / "dist"

# Nombre del ejecutable
OUTPUT_NAME = "Launcher_Windows"

# Carpeta de assets
ASSETS_DIR = PROJECT_ROOT / "assets"

# Archivo de ícono
APP_ICON = ASSETS_DIR / "icon.ico"

# ============================================================================
# DETECCIÓN DE PLATAFORMA
# ============================================================================

def get_platform_config():
    """
    Detecta la plataforma y retorna configuración específica.

    Returns:
        dict: Configuración para la plataforma actual
    """
    platform = sys.platform

    if platform == "win32":
        return {
            "extension": ".exe",
            "console_mode": "disable",
            "icon_supported": True,
            "file_version": LAUNCHER_VERSION,
            "product_version": LAUNCHER_VERSION,
            "file_description": "Launcher y actualizador del Sistema POS",
        }
    elif platform.startswith("linux"):
        return {
            "extension": "",  # Sin extensión en Linux
            "console_mode": None,  # No aplica en Linux
            "icon_supported": False,  # Nuitka en Linux no soporta íconos fácilmente
            "file_version": LAUNCHER_VERSION,
            "product_version": LAUNCHER_VERSION,
            "file_description": "Launcher y actualizador del Sistema POS",
        }
    else:
        # Plataforma desconocida, asumir Linux-like
        return {
            "extension": "",
            "console_mode": None,
            "icon_supported": False,
            "file_version": LAUNCHER_VERSION,
            "product_version": LAUNCHER_VERSION,
            "file_description": "Launcher y actualizador del Sistema POS",
        }


# Configuración de plataforma
PLATFORM_CONFIG = get_platform_config()


# ============================================================================
# OPCIONES DE NUITKA PARA EL LAUNCHER
# ============================================================================

NUITKA_OPTIONS = {
    # Tipo de compilación
    "standalone": True,
    "onefile": True,  # El launcher es un solo archivo

    # Información del ejecutable (solo para Windows)
    "company_name": PLATFORM_CONFIG["file_version"] or None,
    "product_name": PLATFORM_CONFIG["product_version"] or None,
    "file_version": PLATFORM_CONFIG["file_version"] or None,
    "product_version": PLATFORM_CONFIG["file_version"] or None,
    "file_description": PLATFORM_CONFIG["file_description"] or None,

    # Plugins necesarios
    "plugins": [
        "tk-inter",  # Para CustomTkinter
    ],

    # Paquetes a incluir
    "include_packages": [
        "launcher",
        "customtkinter",
    ],

    # Módulos a incluir
    "include_modules": [
        "launcher.resources.config",
        "launcher.resources.utils",
        "launcher.updater",
        "launcher.ui",
    ],

    # Optimizaciones
    "lto": "yes",

    # Sin consola (solo para Windows)
    "windows_console_mode": "disable" if PLATFORM_CONFIG["console_mode"] else None,

    # Aceptar descargas automáticamente (para CI/CD)
    "assume_yes_for_downloads": True,
}


# ============================================================================
# FUNCIONES DE UTILIDAD
# ============================================================================

def print_header(text: str) -> None:
    """Imprime un encabezado formateado."""
    print("\n" + "=" * 60)
    print(f" {text}")
    print("=" * 60)


def print_step(text: str) -> None:
    """Imprime un paso del proceso."""
    print(f"\n>>> {text}")


def run_command(cmd: list, cwd: Path = None) -> bool:
    """
    Ejecuta un comando y muestra la salida en tiempo real.
    
    Args:
        cmd: Lista con el comando y argumentos
        cwd: Directorio de trabajo
    
    Returns:
        True si el comando fue exitoso
    """
    print(f"Ejecutando: {' '.join(cmd)}")
    print("-" * 40)
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=cwd,
            text=True,
            bufsize=1,
        )
        
        # Mostrar salida en tiempo real
        for line in iter(process.stdout.readline, ''):
            print(line, end='')
        
        process.wait()
        return process.returncode == 0
    
    except FileNotFoundError:
        print(f"ERROR: Comando no encontrado: {cmd[0]}")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def clean_build_artifacts() -> None:
    """Limpia artefactos de compilaciones anteriores del launcher."""
    print_step("Limpiando artefactos anteriores del launcher...")
    
    # Carpetas a limpiar
    to_clean = [
        OUTPUT_DIR / f"{OUTPUT_NAME}.dist",
        OUTPUT_DIR / f"{OUTPUT_NAME}.build",
        OUTPUT_DIR / f"{OUTPUT_NAME}.onefile-build",
    ]
    
    # Archivos a limpiar
    files_to_clean = [
        OUTPUT_DIR / f"{OUTPUT_NAME}.exe",
    ]
    
    for path in to_clean:
        if path.exists():
            print(f"  Eliminando: {path}")
            shutil.rmtree(path)
    
    for path in files_to_clean:
        if path.exists():
            print(f"  Eliminando: {path}")
            path.unlink()


def build_nuitka_command() -> list:
    """
    Construye el comando de Nuitka con todas las opciones.
    
    Returns:
        Lista con el comando completo
    """
    cmd = [sys.executable, "-m", "nuitka"]
    
    # Opciones básicas
    if NUITKA_OPTIONS.get("standalone"):
        cmd.append("--standalone")
    
    if NUITKA_OPTIONS.get("onefile"):
        cmd.append("--onefile")
    
    # Información del ejecutable
    if NUITKA_OPTIONS.get("company_name"):
        cmd.append(f"--company-name={NUITKA_OPTIONS['company_name']}")
    
    if NUITKA_OPTIONS.get("product_name"):
        cmd.append(f"--product-name={NUITKA_OPTIONS['product_name']}")
    
    if NUITKA_OPTIONS.get("file_version"):
        cmd.append(f"--file-version={NUITKA_OPTIONS['file_version']}")
    
    if NUITKA_OPTIONS.get("product_version"):
        cmd.append(f"--product-version={NUITKA_OPTIONS['product_version']}")
    
    if NUITKA_OPTIONS.get("file_description"):
        cmd.append(f"--file-description={NUITKA_OPTIONS['file_description']}")
    
    # Plugins
    for plugin in NUITKA_OPTIONS.get("plugins", []):
        cmd.append(f"--enable-plugin={plugin}")
    
    # Paquetes
    for package in NUITKA_OPTIONS.get("include_packages", []):
        cmd.append(f"--include-package={package}")
    
    # Módulos
    for module in NUITKA_OPTIONS.get("include_modules", []):
        cmd.append(f"--include-module={module}")
    
    # Optimizaciones
    if NUITKA_OPTIONS.get("lto"):
        cmd.append(f"--lto={NUITKA_OPTIONS['lto']}")
    
    # Consola (solo Windows)
    if NUITKA_OPTIONS.get("windows_console_mode"):
        cmd.append(f"--windows-console-mode={NUITKA_OPTIONS['windows_console_mode']}")

    # Aceptar descargas automáticamente
    if NUITKA_OPTIONS.get("assume_yes_for_downloads"):
        cmd.append("--assume-yes-for-downloads")

    # Ícono (solo si está soportado)
    if PLATFORM_CONFIG["icon_supported"] and APP_ICON.exists():
        cmd.append(f"--windows-icon-from-ico={APP_ICON}")

    # Directorio de salida
    cmd.append(f"--output-dir={OUTPUT_DIR}")

    # Nombre del ejecutable (con extensión según plataforma)
    output_filename = f"{OUTPUT_NAME}{PLATFORM_CONFIG['extension']}"
    cmd.append(f"--output-filename={output_filename}")

    # Script principal
    cmd.append(str(LAUNCHER_SCRIPT))
    
    return cmd


def build_launcher() -> bool:
    """
    Compila el launcher con Nuitka.
    
    Returns:
        True si la compilación fue exitosa
    """
    print_header("COMPILACIÓN DEL LAUNCHER POS")
    
    # Verificar que existe el script
    if not LAUNCHER_SCRIPT.exists():
        print(f"ERROR: No se encontró {LAUNCHER_SCRIPT}")
        return False
    
    # Crear directorio de salida
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Construir comando
    cmd = build_nuitka_command()
    
    output_filename = f"{OUTPUT_NAME}{PLATFORM_CONFIG['extension']}"
    print_step("Iniciando compilación con Nuitka...")
    print(f"Script: {LAUNCHER_SCRIPT}")
    print(f"Salida: {OUTPUT_DIR / output_filename}")
    print(f"Plataforma: {sys.platform}")

    start_time = time.time()

    # Ejecutar compilación
    success = run_command(cmd, cwd=PROJECT_ROOT)

    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    if success:
        print_header("¡COMPILACIÓN EXITOSA!")
        print(f"Tiempo: {minutes}m {seconds}s")

        # Verificar que se creó el ejecutable
        exe_path = OUTPUT_DIR / output_filename
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print(f"Ejecutable: {exe_path}")
            print(f"Tamaño: {size_mb:.1f} MB")

        print("\nPara probar el launcher:")
        if PLATFORM_CONFIG["extension"]:
            print(f"  .\\dist\\{output_filename}")
        else:
            print(f"  ./dist/{output_filename}")
    else:
        print_header("ERROR EN COMPILACIÓN")
        print("Revisa los mensajes de error arriba.")
    
    return success


def main():
    """Función principal."""
    parser = argparse.ArgumentParser(
        description="Compila el Launcher POS con Nuitka"
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Limpiar artefactos antes de compilar"
    )
    
    args = parser.parse_args()
    
    print_header("BUILD LAUNCHER POS")
    print(f"Python: {sys.version}")
    print(f"Proyecto: {PROJECT_ROOT}")
    print(f"Plataforma: {sys.platform} (extensión: '{PLATFORM_CONFIG['extension']}')")
    
    # Limpiar si se solicita
    if args.clean:
        clean_build_artifacts()
    
    # Compilar
    success = build_launcher()
    
    # Código de salida
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
