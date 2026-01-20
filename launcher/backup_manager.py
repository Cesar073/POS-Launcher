"""
Gestor de Backups del POS.

Este módulo contiene la lógica para:
- Restaurar versiones anteriores desde backups
- Gestionar el proceso de downgrade

Los backups se almacenan en una carpeta "backup" al mismo nivel que la aplicación.
"""

from resources.logging_method import log_simple_class_methods

from resources.config import (
    APP_EXECUTABLE,
    APP_EXECUTABLE_NAME,
    get_app_executable_path,
)
from resources.utils import (
    get_pos_base_dir_windows,
)


class BackupError(Exception):
    """Error durante el proceso de restauración de backup."""
    pass



@log_simple_class_methods
class BackupManager:
    """
    Gestor de backups.
    
    Maneja la restauración de versiones anteriores desde backups.
    """
    
    def __init__(self):
        """Inicializa el gestor de backups."""
        self.pos_base_dir = get_pos_base_dir_windows()
        self.backup_dir = self.pos_base_dir / "backup"
    
    def downgrade(self) -> None:
        """
        Restaura la versión anterior desde el backup.
        
        Raises:
            BackupError: Si ocurre un error durante la restauración.
        """
        # Verificar que existe el directorio de backup
        if not self.backup_dir.exists():
            error_msg = f"No se encontró el directorio de backup: {self.backup_dir}"
            print(f"backup_manager.py: ERROR - {error_msg}")
            raise BackupError(error_msg)
        
        print(f"backup_manager.py: Directorio de backup encontrado: {self.backup_dir}")
        
        # Buscar el ejecutable en el backup
        backup_executable = None
        for file in self.backup_dir.iterdir():
            if file.is_file() and file.name.startswith(APP_EXECUTABLE_NAME) and file.name.endswith(APP_EXECUTABLE):
                backup_executable = file
                break
        
        if backup_executable is None:
            error_msg = f"No se encontró el ejecutable de backup en: {self.backup_dir}"
            print(f"backup_manager.py: ERROR - {error_msg}")
            raise BackupError(error_msg)
        
        print(f"backup_manager.py: Ejecutable de backup encontrado: {backup_executable}")
        
        # Obtener la ruta del ejecutable actual
        current_executable = get_app_executable_path()
        print(f"backup_manager.py: Ejecutable actual: {current_executable}")
        
        # TODO: Implementar la lógica de restauración
        print("backup_manager.py: TODO - Implementar lógica de restauración")
        print("backup_manager.py: BackupManager.downgrade() - Proceso de downgrade completado (simulado)")
