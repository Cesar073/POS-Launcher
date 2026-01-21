"""
Gestor de Backups del POS.

Este módulo contiene la lógica para:
- Crear backups de la aplicación actual
- Restaurar versiones anteriores desde backups
- Gestionar el proceso de downgrade

Los backups se almacenan en una carpeta "backup" al mismo nivel que la aplicación.
"""

import shutil
from pathlib import Path

from resources.logging_method import log_simple_class_methods

from resources.config import (
    APP_EXECUTABLE,
    APP_EXECUTABLE_NAME,
    get_app_executable_path,
)
from resources.utils import (
    get_pos_base_dir_windows,
    has_backups,
    safe_delete,
    is_process_running,
    kill_process,
)


class BackupError(Exception):
    """Error durante el proceso de restauración de backup."""


@log_simple_class_methods
class BackupManager:
    """
    Gestor de backups.
    
    Maneja la creación y restauración de versiones anteriores desde backups.
    
    Métodos principales:
    - create_backup(): Crea un backup de la aplicación actual
    - downgrade(): Restaura la versión anterior desde el backup
    """
    
    def __init__(self):
        """Inicializa el gestor de backups."""
        self.pos_base_dir = get_pos_base_dir_windows()
        self.backup_dir = self.pos_base_dir / "backup"
        self.has_backups = has_backups()

    def create_backup(self) -> bool:
        """
        Crea un backup de la aplicación actual.
        
        Este método:
        1. Limpia la carpeta de backup si ya tiene contenido
        2. Copia todo el contenido de la carpeta principal de POS a la carpeta backup
           (excepto la carpeta backup misma)
        
        Returns:
            True si el backup se creó correctamente.
        
        Raises:
            BackupError: Si ocurre un error durante la creación del backup.
        """
        # Verificar que existe la carpeta principal de POS
        if not self.pos_base_dir.exists():
            raise BackupError(f"La carpeta principal de POS no existe: {self.pos_base_dir}")
        
        # Paso 1: Limpiar la carpeta de backup si ya tiene contenido
        if self.backup_dir.exists():
            self._clean_backup_directory()
        else:
            # Crear la carpeta backup si no existe
            self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Paso 2: Copiar todo desde la carpeta principal a backup
        status_copy = self._copy_pos_to_backup()
        if not status_copy:
            raise BackupError("No se pudo copiar el contenido a la carpeta de backup")
        
        return True
    
    def downgrade(self) -> bool:
        """
        Restaura la versión anterior desde el backup.
        
        Este método:
        1. Cierra la aplicación si está corriendo
        2. Elimina todo lo que hay en la carpeta principal de POS
        3. Copia todo desde backup a la carpeta principal
        4. Limpia la carpeta de backup
        
        Returns:
            True si el downgrade se realizó correctamente.
        
        Raises:
            BackupError: Si ocurre un error durante la restauración.
        """

        if not self.has_backups:
            raise BackupError("No hay backups disponibles")

        # Cerrar la aplicación si está corriendo
        if is_process_running(APP_EXECUTABLE):
            if not kill_process(APP_EXECUTABLE):
                raise BackupError(f"No se pudo cerrar {APP_EXECUTABLE}. Por favor ciérralo manualmente e intenta de nuevo.")
        
        # Paso 1: Eliminar todo lo que hay en la carpeta principal de POS
        self._clear_pos_directory()
        
        # Paso 2: Copiar todo desde backup a la carpeta principal
        status_copy = self._copy_backup_to_pos()
        if not status_copy:
            raise BackupError("No se pudo copiar el backup a la carpeta principal")
        
        # Paso 3: Limpiar la carpeta de backup
        status_clean = self._clean_backup_directory()
        if not status_clean:
            raise BackupError("No se pudo limpiar la carpeta de backup")

        return True

    def _clear_pos_directory(self) -> bool:
        """
        Elimina todo el contenido de la carpeta principal de POS.
        
        Raises:
            BackupError: Si no se puede eliminar algún archivo o directorio.
        """
        if not self.pos_base_dir.exists():
            return False

        # Iterar sobre todos los elementos en el directorio para eliminarlos menos la carpeta backup
        for item in self.pos_base_dir.iterdir():
            try:
                if item.is_file():
                    if not safe_delete(item):
                        raise BackupError(f"No se pudo eliminar el archivo: {item.name}")
                elif item.is_dir():
                    if item.name == "backup":
                        continue
                    shutil.rmtree(item)
            except Exception as e:
                raise BackupError(f"Error eliminando {item.name}: {e}")
        return True
    
    def _copy_pos_to_backup(self) -> bool:
        """
        Copia todo el contenido desde la carpeta principal de POS a la carpeta backup.
        
        Returns:
            True si la copia se realizó correctamente, False en caso contrario.
        
        Raises:
            BackupError: Si no se puede copiar algún archivo o directorio.
        """
        # Iterar sobre todos los elementos en el directorio principal
        for item in self.pos_base_dir.iterdir():
            try:
                # Omitir la carpeta backup para evitar copiarla a sí misma
                if item.name == "backup":
                    continue
                
                destination = self.backup_dir / item.name
                
                if item.is_file():
                    shutil.copy2(item, destination)
                elif item.is_dir():
                    if destination.exists():
                        shutil.rmtree(destination)
                    shutil.copytree(item, destination)
            except Exception as e:
                raise BackupError(f"Error copiando {item.name} al backup: {e}")
        
        return True
    
    def _copy_backup_to_pos(self) -> bool:
        """
        Copia todo el contenido desde la carpeta backup a la carpeta principal de POS.
        
        Returns:
            True si la copia se realizó correctamente, False en caso contrario.
        
        Raises:
            BackupError: Si no se puede copiar algún archivo o directorio.
        """
        if not self.backup_dir.exists():
            raise BackupError(f"El directorio de backup no existe: {self.backup_dir}")
        
        # Asegurar que el directorio principal existe
        self.pos_base_dir.mkdir(parents=True, exist_ok=True)
        
        # Iterar sobre todos los elementos en el directorio de backup
        for item in self.backup_dir.iterdir():
            try:
                destination = self.pos_base_dir / item.name
                
                if item.is_file():
                    shutil.copy2(item, destination)
                elif item.is_dir():
                    if destination.exists():
                        shutil.rmtree(destination)
                    shutil.copytree(item, destination)
            except Exception as e:
                raise BackupError(f"Error copiando {item.name}: {e}")
        
        return True
    
    def _clean_backup_directory(self) -> bool:
        """
        Limpia todo el contenido de la carpeta de backup.
        """
        # Iterar sobre todos los elementos en el directorio de backup para eliminarlos
        for item in self.backup_dir.iterdir():
            try:
                if item.is_file():
                    print(f"backup_manager.py: Eliminando archivo de backup: {item.name}")
                    if not safe_delete(item):
                        error_msg = f"No se pudo eliminar el archivo de backup: {item.name}"
                        print(f"backup_manager.py: ERROR - {error_msg}")
                        raise BackupError(error_msg)
                elif item.is_dir():
                    print(f"backup_manager.py: Eliminando directorio de backup: {item.name}")
                    shutil.rmtree(item)
            except Exception as e:
                error_msg = f"Error eliminando {item.name} del backup: {e}"
                print(f"backup_manager.py: ERROR - {error_msg}")
                raise BackupError(error_msg)
        
        return True
        