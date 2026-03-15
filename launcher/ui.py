"""
Interfaz gráfica del Launcher.

Ventana de actualización usando CustomTkinter con:
- Información de la nueva versión
- Changelog/notas de la versión
- Barra de progreso para descarga
- Botones para actualizar, restaurar versión anterior y omitir
"""

import customtkinter as ctk
from typing import Optional, Callable
import threading

from resources.config import (
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_TITLE,
    THEME_PRIMARY,
    THEME_SUCCESS,
    THEME_ERROR,
    ALLOW_SKIP_UPDATE,
    get_app_executable_path
)
from updater import Updater, UpdateInfo, UpdateError
from backup_manager import BackupManager, BackupError

from resources.utils import start_application

class LauncherUI(ctk.CTk):
    """
    Ventana principal del launcher.
    
    Muestra información sobre actualizaciones disponibles y
    permite al usuario:
    - Actualizar la aplicación
    - Restaurar la versión anterior
    - Omitir la actualización (Abre POS.exe sin actualizar)
    - Cerrar la ventana (Cierra el launcher y abre POS.exe)
    """
    
    def __init__(
        self,
        updater: Updater,
        update_info: Optional[UpdateInfo] = None,
        check_callback: Optional[Callable[[], None]] = None,
        has_backups_available: bool = False,
    ):
        """
        Inicializa la ventana del launcher.
        
        Args:
            updater: Instancia del Updater
            update_info: Información de la actualización disponible (None si está buscando)
            check_callback: Callback para iniciar la búsqueda de actualizaciones (se llamará después del delay)
            has_backups_available: Indica si hay backups disponibles
        """
        super().__init__()
        
        self.updater = updater
        self.update_info = update_info
        self.check_callback = check_callback
        self.has_backups_available = has_backups_available
        
        # Crear instancia de BackupManager (siempre disponible)
        self.backup_manager = BackupManager()
        
        self._is_updating = False
        self._is_checking = update_info is None
        
        # Configurar ventana
        self._setup_window()
        
        # Crear widgets
        self._create_widgets()
        
        # Forzar actualización del layout después de crear todos los widgets
        self.after(100, self._apply_button_sizing)
        
        # Si está en modo "buscando", configurar UI inicial
        if self._is_checking:
            self._show_checking_state()
            # Programar la búsqueda de actualizaciones después de 1.5 segundos
            if self.check_callback:
                self.after(1500, self._start_checking)
    
    def _setup_window(self) -> None:
        """Configura la ventana principal."""
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.resizable(False, False)
        
        # Centrar ventana
        self.update_idletasks()
        x = (self.winfo_screenwidth() - WINDOW_WIDTH) // 2
        y = (self.winfo_screenheight() - WINDOW_HEIGHT) // 2
        self.geometry(f"+{x}+{y}")
        
        # Configurar tema
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Manejar cierre de ventana
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self) -> None:
        """Crea todos los widgets de la interfaz."""
        # Frame principal con padding
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # === Encabezado ===
        self._create_header()
        
        # === Información de versión ===
        self._create_version_info()
        
        # === Changelog ===
        self._create_changelog()
        
        # === Barra de progreso (oculta inicialmente) ===
        self._create_progress_section()
        
        # === Botones ===
        self._create_buttons()
    
    def _create_header(self) -> None:
        """Crea el encabezado con título."""
        header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        header_frame.pack(fill="x", pady=(0, 15))
        
        # Ícono o título grande
        self.title_label = ctk.CTkLabel(
            header_frame,
            text="🔄 Actualización Disponible",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self.title_label.pack()
        
        # Subtítulo
        self.subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Hay una nueva versión del Sistema POS",
            font=ctk.CTkFont(size=13),
            text_color="gray",
        )
        self.subtitle_label.pack(pady=(5, 0))
    
    def _show_checking_state(self) -> None:
        """Muestra el estado de búsqueda de actualizaciones."""
        self.title_label.configure(text="🔍 Buscando Actualizaciones...")
        self.subtitle_label.configure(
            text="Verificando si hay nuevas versiones disponibles",
            text_color="gray",
        )
        
        # Ocultar widgets que no se necesitan mientras busca
        if hasattr(self, 'version_frame'):
            self.version_frame.pack_forget()
        if hasattr(self, 'changelog_frame'):
            self.changelog_frame.pack_forget()
        if hasattr(self, 'button_frame'):
            self.button_frame.pack_forget()
        
        # Mostrar barra de progreso indeterminada
        if hasattr(self, 'progress_frame'):
            self.progress_frame.pack(fill="x", pady=(0, 15))
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start()
            self.status_label.configure(text="Buscando actualizaciones...")
            self.progress_label.configure(text="")
    
    def update_with_result(self, update_info: Optional[UpdateInfo]) -> None:
        """
        Actualiza la UI con el resultado de la búsqueda de actualizaciones.
        
        Args:
            update_info: Información de actualización o None si no hay actualización
        """
        self.update_info = update_info
        self._is_checking = False
        
        # Detener barra de progreso
        if hasattr(self, 'progress_bar'):
            self.progress_bar.stop()
            self.progress_frame.pack_forget()
        
        if update_info:
            # Hay actualización disponible
            self.title_label.configure(text="🔄 Actualización Disponible")
            self.subtitle_label.configure(
                text="Hay una nueva versión del Sistema POS",
                text_color="gray",
            )
            
            # Mostrar widgets de actualización
            if hasattr(self, 'version_frame'):
                self.version_frame.pack(fill="x", pady=(0, 15))
            if hasattr(self, 'changelog_frame'):
                self.changelog_frame.pack(fill="both", expand=True, pady=(0, 15))
            if hasattr(self, 'button_frame'):
                self.button_frame.pack(fill="x")
            
            # Actualizar información de versión
            self._update_version_info()
            self._update_changelog()
        else:
            # No hay actualización - iniciar app directamente
            self.destroy()
    
    def _update_version_info(self) -> None:
        """Actualiza la información de versión en la UI."""
        if self.update_info:
            # Mostrar flecha y nueva versión
            self.arrow_label.grid(row=0, column=1)
            self.new_version_frame.grid(row=0, column=2, padx=15, pady=15)
            self.new_version_label.configure(text=f"v{self.update_info.version}")
        else:
            # Ocultar flecha y nueva versión
            self.arrow_label.grid_remove()
            self.new_version_frame.grid_remove()
    
    def _update_changelog(self) -> None:
        """Actualiza el changelog en la UI."""
        if self.update_info and hasattr(self, 'changelog_text'):
            self.changelog_text.configure(state="normal")
            self.changelog_text.delete("1.0", "end")
            changelog = self.update_info.changelog or "Sin descripción disponible"
            self.changelog_text.insert("1.0", changelog)
            self.changelog_text.configure(state="disabled")
    
    def _start_app_and_close(self) -> None:
        """Inicia la app y cierra la ventana."""
        self.destroy()
    
    def _start_checking(self) -> None:
        """Inicia la búsqueda de actualizaciones (llamado después del delay inicial)."""
        if self.check_callback:
            self.check_callback()
    
    def _create_version_info(self) -> None:
        """Crea la sección de información de versión."""
        self.version_frame = ctk.CTkFrame(self.main_frame)
        self.version_frame.pack(fill="x", pady=(0, 15))
        
        # Grid para las versiones
        self.version_frame.grid_columnconfigure(0, weight=1)
        self.version_frame.grid_columnconfigure(1, weight=0)
        self.version_frame.grid_columnconfigure(2, weight=1)
        
        # Versión actual
        current_frame = ctk.CTkFrame(self.version_frame, fg_color="transparent")
        current_frame.grid(row=0, column=0, padx=15, pady=15)
        
        ctk.CTkLabel(
            current_frame,
            text="Versión actual",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack()
        
        if self.updater.current_version is None:
            current_version_label = "Sin instalación"
        else:
            current_version_label = f"v{self.updater.current_version}"
        ctk.CTkLabel(
            current_frame,
            text=current_version_label,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack()
        
        # Flecha (solo se muestra si hay actualización)
        self.arrow_label = ctk.CTkLabel(
            self.version_frame,
            text="→",
            font=ctk.CTkFont(size=24),
            text_color=THEME_PRIMARY,
        )
        
        # Nueva versión
        self.new_version_frame = ctk.CTkFrame(self.version_frame, fg_color="transparent")
        
        ctk.CTkLabel(
            self.new_version_frame,
            text="Nueva versión",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        ).pack()
        
        self.new_version_label = ctk.CTkLabel(
            self.new_version_frame,
            text="",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=THEME_SUCCESS,
        )
        self.new_version_label.pack()
        
        # Solo mostrar nueva versión si hay update_info
        if self.update_info:
            self._update_version_info()
    
    def _create_changelog(self) -> None:
        """Crea la sección del changelog."""
        self.changelog_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.changelog_frame.pack(fill="both", expand=True, pady=(0, 15))
        
        # Título
        ctk.CTkLabel(
            self.changelog_frame,
            text="📋 Notas de la versión:",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x")
        
        # Área de texto para el changelog
        self.changelog_text = ctk.CTkTextbox(
            self.changelog_frame,
            font=ctk.CTkFont(size=12),
            wrap="word",
            height=120,
        )
        self.changelog_text.pack(fill="both", expand=True, pady=(8, 0))
        
        # Insertar changelog solo si hay update_info
        if self.update_info:
            changelog = self.update_info.changelog or "Sin descripción disponible"
            self.changelog_text.insert("1.0", changelog)
        self.changelog_text.configure(state="disabled")  # Solo lectura
    
    def _create_progress_section(self) -> None:
        """Crea la sección de progreso (oculta inicialmente)."""
        self.progress_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        # No se empaqueta aquí, se mostrará durante la descarga
        
        # Etiqueta de estado
        self.status_label = ctk.CTkLabel(
            self.progress_frame,
            text="Descargando actualización...",
            font=ctk.CTkFont(size=12),
        )
        self.status_label.pack(fill="x")
        
        # Barra de progreso
        self.progress_bar = ctk.CTkProgressBar(
            self.progress_frame,
            mode="determinate",
        )
        self.progress_bar.pack(fill="x", pady=(8, 0))
        self.progress_bar.set(0)
        
        # Porcentaje
        self.progress_label = ctk.CTkLabel(
            self.progress_frame,
            text="0%",
            font=ctk.CTkFont(size=11),
            text_color="gray",
        )
        self.progress_label.pack(pady=(5, 0))
    
    def _create_buttons(self) -> None:
        """Crea los botones de acción."""
        self.button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        # Aumentar padding vertical para que los botones no se corten
        self.button_frame.pack(fill="x", pady=(10, 10))
        
        # Configurar grid del frame
        # Configuramos hasta 3 columnas: 0 y 1 para botones secundarios, 2 para botón principal
        self.button_frame.grid_columnconfigure(0, weight=1)  # Columna izquierda (botones secundarios)
        self.button_frame.grid_columnconfigure(1, weight=0)  # Columna media (botones secundarios)
        self.button_frame.grid_columnconfigure(2, weight=0)  # Columna derecha (botón actualizar)
        
        column = 0
        
        # Botón secundario: Omitir (si está permitido)
        if ALLOW_SKIP_UPDATE:
            self.skip_button = ctk.CTkButton(
                self.button_frame,
                text="Omitir por ahora",
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                border_width=1,
                text_color=("gray70", "gray30"),
                hover_color=("gray20", "gray80"),
                command=self._on_skip_clicked,
                width=150,  # Aumentado de 140 a 150 para que el texto no se corte
                height=40,
                corner_radius=8,
            )
            self.skip_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        
        # Botón de restaurar backup (si hay backups disponibles)
        if self.has_backups_available:
            self.restore_button = ctk.CTkButton(
                self.button_frame,
                text="Restaurar versión anterior",
                font=ctk.CTkFont(size=13),
                fg_color="transparent",
                border_width=1,
                text_color=("gray70", "gray30"),
                hover_color=("gray20", "gray80"),
                command=self._on_restore_clicked,
                width=170,  # Reducido de 180 a 170 para balancear el espacio
                height=40,
                corner_radius=8,
            )
            self.restore_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        
        # Botón principal: Actualizar
        self.update_button = ctk.CTkButton(
            self.button_frame,
            text="Actualizar ahora",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME_PRIMARY,
            hover_color="#1557b0",
            command=self._on_update_clicked,
            width=150,  # Reducido de 160 a 150 para balancear el espacio
            height=40,
            corner_radius=8,
        )
        self.update_button.grid(row=0, column=2, padx=0, pady=(10, 10), sticky="e")
    
    def _apply_button_sizing(self) -> None:
        """Re-aplica el tamaño de los botones para asegurar que se vean correctamente."""
        # Con grid no necesitamos re-aplicar, pero podemos forzar actualización
        self.update_idletasks()
    
    def _on_update_clicked(self) -> None:
        """Maneja clic en botón Actualizar."""
        if self._is_updating:
            return
        
        self._is_updating = True
        self._start_update_ui()
        
        # Iniciar descarga en hilo separado
        thread = threading.Thread(target=self._download_and_apply, daemon=True)
        thread.start()
    
    def _start_update_ui(self) -> None:
        """Actualiza la UI para mostrar el progreso."""
        # Ocultar botones
        if hasattr(self, 'skip_button'):
            self.skip_button.grid_remove()
        if hasattr(self, 'restore_button'):
            self.restore_button.grid_remove()
        self.update_button.grid_remove()
        
        # Ocultar changelog y mostrar progreso
        self.changelog_text.master.pack_forget()
        self.progress_frame.pack(fill="x", pady=(0, 15))
        
        # Configurar callback de progreso
        self.updater.set_progress_callback(self._update_progress)
    
    def _update_progress(self, downloaded: int, total: int) -> None:
        """
        Actualiza la barra de progreso.
        
        Args:
            downloaded: Bytes descargados
            total: Bytes totales
        """
        if total > 0:
            progress = downloaded / total
            percentage = int(progress * 100)
            
            # Actualizar en el hilo principal
            self.after(0, lambda: self._set_progress(progress, percentage, downloaded, total))
    
    def _set_progress(self, progress: float, percentage: int, downloaded: int, total: int) -> None:
        """Actualiza los widgets de progreso (debe llamarse desde el hilo principal)."""
        self.progress_bar.set(progress)
        
        # Formatear tamaños
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total / (1024 * 1024)
        
        self.progress_label.configure(
            text=f"{percentage}% ({downloaded_mb:.1f} MB / {total_mb:.1f} MB)"
        )
    
    def _download_and_apply(self) -> None:
        """Descarga y aplica la actualización (ejecuta en hilo separado)."""
        backup_created = False
        try:
            # Crear backup si hay una versión instalada
            if self.updater.current_version is not None:
                self.after(0, lambda: self.status_label.configure(text="Creando backup de la versión actual..."))
                self.after(0, lambda: self.progress_bar.configure(mode="indeterminate"))
                self.after(0, lambda: self.progress_bar.start())
                
                try:
                    self.backup_manager.create_backup()
                    # Detener la barra antes de continuar
                    self.after(0, lambda: self.progress_bar.stop())
                except BackupError as e:
                    # Si falla el backup, continuar con la actualización pero mostrar advertencia
                    self.after(0, lambda: self.progress_bar.stop())
            
            # Descargar
            self.after(0, lambda: self.status_label.configure(text="Descargando actualización..."))
            self.after(0, lambda: self.progress_bar.configure(mode="determinate"))
            self.after(0, lambda: self.progress_bar.set(0))
            self.updater.download_update()
            
            # Aplicar
            self.after(0, lambda: self.status_label.configure(text="Instalando actualización..."))
            self.after(0, lambda: self.progress_bar.configure(mode="indeterminate"))
            self.after(0, lambda: self.progress_bar.start())

            # Crear backup
            try:
                backup_created = self.backup_manager.create_backup()
            except BackupError as e:
                pass

            # Aplicar actualización
            self.updater.apply_update()

            # Éxito
            self.after(0, self._on_update_success)
        
        except Exception as e:
            if backup_created:
                self.backup_manager.downgrade()
            error_msg = f"Error inesperado: {e}"
            self.after(0, lambda msg=error_msg: self._on_update_error(msg))
    
    def _on_update_success(self) -> None:
        """Maneja actualización exitosa."""
        self.progress_bar.stop()
        
        self.status_label.configure(
            text="✅ ¡Actualización completada!",
            text_color=THEME_SUCCESS,
        )
        self.progress_label.configure(text="Iniciando aplicación...")
        
        # Limpiar archivos temporales
        self.updater.cleanup()
        
        # Esperar un momento y cerrar
        self.after(1500, self._finish_update)
    
    def _finish_update(self) -> None:
        """Finaliza la actualización y cierra."""
        self.destroy()
    
    def _on_update_error(self, error_message: str) -> None:
        """
        Maneja error durante la actualización.
        
        Args:
            error_message: Mensaje de error
        """
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        
        self.status_label.configure(
            text=f"❌ Error: {error_message}",
            text_color=THEME_ERROR,
        )
        self.progress_label.configure(text="")
        
        # Ocultar progreso y mostrar changelog de nuevo
        self.progress_frame.pack_forget()
        if hasattr(self, 'changelog_text'):
            self.changelog_text.master.pack(fill="both", expand=True, pady=(0, 15))
        
        # Volver a mostrar y rehabilitar botones
        self._is_updating = False
        column = 0
        if hasattr(self, 'skip_button'):
            self.skip_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        if hasattr(self, 'restore_button'):
            self.restore_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        self.update_button.configure(text="Reintentar")
        self.update_button.grid(row=0, column=2, padx=0, pady=(10, 10), sticky="e")
        
        # Limpiar archivos temporales
        self.updater.cleanup()
    
    def _on_skip_clicked(self) -> None:
        """Maneja clic en botón Omitir."""
        if self._is_updating:
            return
        
        self.destroy()
    
    def _on_restore_clicked(self) -> None:
        """Maneja clic en botón Restaurar versión anterior."""
        if self._is_updating:
            return
        
        self._is_updating = True
        self._start_restore_ui()
        
        # Iniciar downgrade en hilo separado
        thread = threading.Thread(target=self._restore_backup, daemon=True)
        thread.start()
    
    def _start_restore_ui(self) -> None:
        """Actualiza la UI para mostrar el progreso de restauración."""
        # Ocultar botones
        if hasattr(self, 'skip_button'):
            self.skip_button.grid_remove()
        if hasattr(self, 'restore_button'):
            self.restore_button.grid_remove()
        self.update_button.grid_remove()
        
        # Ocultar changelog y mostrar progreso
        if hasattr(self, 'changelog_text'):
            self.changelog_text.master.pack_forget()
        self.progress_frame.pack(fill="x", pady=(0, 15))
        
        # Configurar barra de progreso como indeterminada
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.status_label.configure(text="Restaurando versión anterior...")
        self.progress_label.configure(text="")

    def _restore_backup(self) -> None:
        """Restaura el backup (ejecuta en hilo separado)."""
        try:
            status_downgrade = self.backup_manager.downgrade()
            if not status_downgrade:
                raise BackupError("No se pudo restaurar la versión anterior")

            # Éxito
            self.after(0, self._on_restore_success)
        
        except BackupError as e:
            error_msg = str(e)
            self.after(0, lambda msg=error_msg: self._on_restore_error(msg))
        except Exception as e:
            error_msg = f"Error inesperado: {e}"
            self.after(0, lambda msg=error_msg: self._on_restore_error(msg))
    
    def _on_restore_success(self) -> None:
        """Maneja restauración exitosa."""
        self.progress_bar.stop()
        
        self.status_label.configure(
            text="✅ ¡Versión anterior restaurada!",
            text_color=THEME_SUCCESS,
        )
        self.progress_label.configure(text="Iniciando aplicación...")
        
        # Iniciar la aplicación        
        app_path = get_app_executable_path()
        if app_path.exists():
            start_application(app_path)
        else:
            raise BackupError(f"No se encontró {app_path}")
        
        # Esperar un momento y cerrar
        self.after(1500, self._finish_restore)
    
    def _finish_restore(self) -> None:
        """Finaliza la restauración y cierra."""
        self.destroy()
    
    def _on_restore_error(self, error_message: str) -> None:
        """
        Maneja error durante la restauración.
        
        Args:
            error_message: Mensaje de error
        """
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        
        self.status_label.configure(
            text=f"❌ Error: {error_message}",
            text_color=THEME_ERROR,
        )
        self.progress_label.configure(text="")
        
        # Ocultar progreso y mostrar changelog de nuevo
        self.progress_frame.pack_forget()
        if hasattr(self, 'changelog_text'):
            self.changelog_text.master.pack(fill="both", expand=True, pady=(0, 15))
        
        # Volver a mostrar y rehabilitar botones
        self._is_updating = False
        column = 0
        if hasattr(self, 'skip_button'):
            self.skip_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        if hasattr(self, 'restore_button'):
            self.restore_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        self.update_button.grid(row=0, column=2, padx=0, pady=(10, 10), sticky="e")
    
    def _on_close(self) -> None:
        """Maneja cierre de ventana."""
        if self._is_updating:
            # No permitir cerrar durante actualización
            return
        
        self.destroy()
