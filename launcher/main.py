"""
Punto de entrada del Launcher POS.

Este es el ejecutable que el usuario final ejecuta.
El launcher:
1. Muestra una splash screen
2. Verifica si hay actualizaciones disponibles de la aplicación POS.
3. Si hay actualización: muestra UI para actualizar la aplicación.
4. Si no hay: muestra la ventana unos segundos y después inicia POS.exe
5. Si el usuario cierra la ventana: no inicia POS.exe
6. Si el usuario omite: inicia POS.exe

Uso:
    python -m launcher.main
    # o directamente:
    python launcher/main.py
"""

import sys
import json
import logging

from updater import Updater, UpdateError, user_message_for_failed_update_check
from resources.config import (
    APP_EXECUTABLE,
)
from resources.utils import (
    start_application,
    get_pos_base_dir_windows,
    has_backups,
    load_launcher_credentials,
)
from ui import LauncherUI
from resources.logging_method import log_function
from resources.exception_logging import (
    install_exception_logging,
    log_exception,
    log_message,
    upload_error_log,
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
def run_launcher() -> bool:
    """
    Función principal del launcher.

    Returns:
        True si hay que abrir el POS al salir de la ventana.
    """
    current_version = get_installed_version_of_pos()
    has_backups_available = has_backups()
    credentials = load_launcher_credentials()
    updater = Updater(
        current_version,
        customer_uuid=credentials.customer_uuid,
        installation_token=credentials.installation_token,
        installation_id=credentials.installation_id,
    )
    needs_activation = not updater.has_auth()

    # Función para buscar actualizaciones (se ejecutará después del delay)
    def check_for_updates():
        update_info = None
        check_failed_message = None
        check_failed_title = None
        show_activation = False
        try:
            updater.reload_credentials()
            if not updater.has_auth():
                show_activation = True
                check_failed_message = (
                    "Ingresá el código de activación para identificar esta instalación."
                )
            else:
                update_info = updater.check_for_updates()
        except UpdateError as e:
            log_exception(e, context="check_for_updates: UpdateError")
            check_failed_message = user_message_for_failed_update_check(e)
            if getattr(e, "license_block", False):
                check_failed_title = "Actualizaciones no disponibles"
            elif e.status_code == 401:
                show_activation = True
                check_failed_title = None
        except Exception as e:
            log_exception(e, context="check_for_updates: Exception")
            check_failed_message = (
                "No se pudo verificar actualizaciones por un error inesperado.\n\n"
                "Puedes reintentar o continuar con la versión instalada. "
                "Si el problema continúa, revisa el archivo de registro del launcher."
            )
        try:
            launcher_ui.update_with_result(
                update_info,
                check_failed_message=check_failed_message,
                check_failed_title=check_failed_title,
                show_activation=show_activation,
            )
        except Exception as e:
            log_exception(e, context="check_for_updates: update_with_result")
            raise
    
    # Mostrar ventana del launcher en modo "buscando"
    launcher_ui = LauncherUI(
        updater=updater,
        update_info=None,  # None indica que está buscando
        check_callback=check_for_updates,
        has_backups_available=has_backups_available,
        needs_activation=needs_activation,
    )
    
    # Ejecutar loop de la UI (esto bloqueará hasta que se cierre la ventana)
    # La búsqueda de actualizaciones se iniciará automáticamente después de 0.5 segundos
    launcher_ui.mainloop()
    return launcher_ui.launch_pos_on_close


@log_function
def main():
    """
    Punto de entrada principal.
    
    Maneja excepciones a nivel global para evitar crashes silenciosos.
    """
    install_exception_logging()
    try:
        credentials = load_launcher_credentials()
        log_message(
            logging.INFO,
            "Diagnóstico: token de instalación: %s | UUID legado: %s",
            bool(credentials.installation_token),
            bool(credentials.customer_uuid),
        )
        launch_pos = True
        try:
            launch_pos = run_launcher()
        except KeyboardInterrupt:
            print("\nLauncher cancelado por el usuario")
            sys.exit(0)
        except Exception as e:
            import traceback

            log_exception(e, context="main: run_launcher")
            traceback.print_exc()

        if not launch_pos:
            return

        try:
            start_pos_application()
        except Exception as e:
            log_exception(e, context="main: start_pos_application")
            raise
    finally:
        upload_error_log()


if __name__ == "__main__":
    main()
