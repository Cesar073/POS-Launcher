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
)
from resources.utils import start_application, get_pos_base_dir_windows
from ui import LauncherUI


POS_BASE_DIR = get_pos_base_dir_windows()


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


def start_pos_application() -> None:
    """
    Inicia la aplicación POS principal.
    """
    
    app_path = get_app_executable_path()
    
    if app_path.exists():
        print(f"Iniciando {app_path}...")
        start_application(app_path)
    else:
        print(f"ERROR: No se encontró {app_path}")
        #input("Presiona Enter para cerrar...")


def run_launcher():
    """
    Función principal del launcher.
    """
    # Obtener versión actual
    current_version = get_installed_version_of_pos()
    if current_version is None:
        print("No se encontró una versión instalada")
    else:
        print(f"Versión instalada: {current_version}")
    
    # Crear updater
    updater = Updater(current_version)

    # Variable para controlar si se debe iniciar la app
    should_start_app = True

    # Callbacks para la UI
    def on_update_complete():
        nonlocal should_start_app
        should_start_app = True
    
    def on_skip():
        nonlocal should_start_app
        should_start_app = True
    
    def on_start_app():
        nonlocal should_start_app
        should_start_app = True
    
    # Función para buscar actualizaciones (se ejecutará después del delay)
    def check_for_updates():
        print("main.py: check_for_updates")
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
        on_update_complete=on_update_complete,
        on_skip=on_skip,
        on_start_app=on_start_app,
        check_callback=check_for_updates,
    )
    
    # Ejecutar loop de la UI (esto bloqueará hasta que se cierre la ventana)
    # La búsqueda de actualizaciones se iniciará automáticamente después de 0.5 segundos
    launcher_ui.mainloop()
    
    # Iniciar la aplicación principal
    if should_start_app:
        start_pos_application()


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
        print(f"Error fatal en launcher: {e}")
        import traceback
        traceback.print_exc()
        # Intentar iniciar la app de todas formas
        start_pos_application()


if __name__ == "__main__":
    main()
