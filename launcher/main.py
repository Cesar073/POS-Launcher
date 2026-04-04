"""
Punto de entrada del Launcher POS.

Este es el ejecutable que el usuario final ejecuta.
El launcher:
1. Muestra una splash screen
2. Verifica si hay actualizaciones disponibles de la aplicación POS.
3. Si hay actualización: muestra UI para actualizar la aplicación.
4. Si no hay o el usuario omite: inicia POS.exe

Uso:
    python -m launcher.main
    # o directamente:
    python launcher/main.py
"""

import sys
import json
import logging

from updater import Updater, UpdateError
from resources.config import (
    APP_EXECUTABLE,
    GITHUB_TOKEN,
)
from resources.utils import start_application, get_pos_base_dir_windows, has_backups
from ui import LauncherUI
from resources.logging_method import log_function
from resources.exception_logging import (
    install_exception_logging,
    log_exception,
    log_message,
)


POS_BASE_DIR = get_pos_base_dir_windows()


@log_function
def get_installed_version_of_pos() -> str | None:
    """
    Obtiene la versión instalada de la aplicación POS.
    """
    if not POS_BASE_DIR.exists():
        return None
    
    version_file = POS_BASE_DIR / "version.json"
    if not version_file.exists():
        return None
    
    with open(version_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get("version") if data else None


@log_function
def start_pos_application() -> None:
    """
    Inicia la aplicación POS principal.
    """
    
    app_path = POS_BASE_DIR / "POS" / APP_EXECUTABLE
    
    if app_path.exists():
        start_application(app_path)
    else:
        print(f"ERROR: No se encontró {app_path}")


@log_function
def run_launcher():
    """
    Función principal del launcher.
    """
    current_version = get_installed_version_of_pos()
    has_backups_available = has_backups()
    updater = Updater(current_version)

    # Función para buscar actualizaciones (se ejecutará después del delay)
    def check_for_updates():
        update_info = None
        try:
            update_info = updater.check_for_updates()
        except UpdateError as e:
            print(f"(x001) Error verificando actualizaciones: {e}")
            log_exception(e, context="check_for_updates: UpdateError")
        except Exception as e:
            print(f"(x002) Error verificando actualizaciones: {e}")
            log_exception(e, context="check_for_updates: Exception")
        try:
            launcher_ui.update_with_result(update_info)
        except Exception as e:
            log_exception(e, context="check_for_updates: update_with_result")
            raise
    
    # Mostrar ventana del launcher en modo "buscando"
    launcher_ui = LauncherUI(
        updater=updater,
        update_info=None,  # None indica que está buscando
        check_callback=check_for_updates,
        has_backups_available=has_backups_available,
    )
    
    # Ejecutar loop de la UI (esto bloqueará hasta que se cierre la ventana)
    # La búsqueda de actualizaciones se iniciará automáticamente después de 0.5 segundos
    launcher_ui.mainloop()


@log_function
def main():
    """
    Punto de entrada principal.
    
    Maneja excepciones a nivel global para evitar crashes silenciosos.
    """
    install_exception_logging()
    log_message(
        logging.INFO,
        "Diagnóstico: GITHUB_TOKEN definido en entorno: %s",
        bool(GITHUB_TOKEN and str(GITHUB_TOKEN).strip()),
    )
    try:
        run_launcher()
    except KeyboardInterrupt:
        print("\nLauncher cancelado por el usuario")
        sys.exit(0)
    except Exception as e:
        import traceback

        log_exception(e, context="main: run_launcher")
        traceback.print_exc()

    # Independientemente del resultado, iniciar la aplicación
    try:
        start_pos_application()
    except Exception as e:
        log_exception(e, context="main: start_pos_application")
        raise


if __name__ == "__main__":
    main()
