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

from updater import Updater, UpdateError
from resources.config import (
    get_app_executable_path,
    APP_EXECUTABLE_NAME,
    APP_EXECUTABLE,
)
from resources.utils import start_application, get_pos_base_dir_windows
from ui import LauncherUI
from resources.logging_method import log_function


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
    
    app_path = get_app_executable_path()
    
    if app_path.exists():
        start_application(app_path)
    else:
        print(f"ERROR: No se encontró {app_path}")


@log_function
def has_backups() -> bool:
    """
    Verifica si hay backups disponibles.
    """
    if not POS_BASE_DIR.exists():
        return False
    
    backup_dir = POS_BASE_DIR / "backup"
    if not backup_dir.exists():
        return False
    
    for file in backup_dir.iterdir():
        if file.is_file() and file.name.startswith(APP_EXECUTABLE_NAME) and file.name.endswith(APP_EXECUTABLE):
            return True
    return False


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
            print(f"Error verificando actualizaciones: {e}")
        except Exception as e:
            print(f"Error verificando actualizaciones: {e}")
        
        # Actualizar la UI con el resultado
        launcher_ui.update_with_result(update_info)
    
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
    try:
        run_launcher()
    except KeyboardInterrupt:
        print("\nLauncher cancelado por el usuario")
        sys.exit(0)
    except Exception as e:
        import traceback
        traceback.print_exc()

    # Independientemente del resultado, iniciar la aplicación
    start_pos_application()


if __name__ == "__main__":
    main()
