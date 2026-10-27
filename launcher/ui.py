"""
Interfaz gráfica del Launcher.

Ventana de actualización usando CustomTkinter con:
- Información de la nueva versión
- Changelog/notas de la versión
- Barra de progreso para descarga
- Botones para actualizar, restaurar versión anterior y omitir
"""

import math
import time
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
    THEME_WARNING,
    ALLOW_SKIP_UPDATE,
    UP_TO_DATE_REDIRECT_MS,
    get_app_executable_path
)
from updater import Updater, UpdateInfo, UpdateError, user_message_for_activation
from backup_manager import BackupManager, BackupError

from resources.utils import start_application
from resources.exception_logging import get_log_file_path, log_exception
from resources.version import get_version

class LauncherUI(ctk.CTk):
    """
    Ventana principal del launcher.
    
    Muestra información sobre actualizaciones disponibles y
    permite al usuario:
    - Actualizar la aplicación
    - Restaurar la versión anterior
    - Omitir la actualización (abre POS.exe sin actualizar)
    - Cerrar la ventana (cierra el launcher sin abrir POS.exe)
    """
    
    def __init__(
        self,
        updater: Updater,
        update_info: Optional[UpdateInfo] = None,
        check_callback: Optional[Callable[[], None]] = None,
        has_backups_available: bool = False,
        needs_activation: bool = False,
    ):
        """
        Inicializa la ventana del launcher.
        
        Args:
            updater: Instancia del Updater
            update_info: Información de la actualización disponible (None si está buscando)
            check_callback: Callback para iniciar la búsqueda de actualizaciones (se llamará después del delay)
            has_backups_available: Indica si hay backups disponibles
            needs_activation: Pide un código antes de consultar actualizaciones
        """
        super().__init__()
        
        self.updater = updater
        self.update_info = update_info
        self.check_callback = check_callback
        self.has_backups_available = has_backups_available
        self._needs_activation = needs_activation
        
        # Crear instancia de BackupManager (siempre disponible)
        self.backup_manager = BackupManager()
        
        self._is_updating = False
        self._is_activating = False
        self._is_checking = update_info is None and not needs_activation
        self.launch_pos_on_close = False
        self._redirect_after_id = None
        self._redirect_cancelled = False
        
        # Configurar ventana
        self._setup_window()
        
        # Crear widgets
        self._create_widgets()
        
        # Forzar actualización del layout después de crear todos los widgets
        self.after(100, self._apply_button_sizing)
        
        if self._needs_activation:
            self._show_activation_state()
        elif self._is_checking:
            self._show_checking_state()
            # Programar la búsqueda de actualizaciones después de 1.5 segundos
            if self.check_callback:
                self.after(1500, self._start_checking)
    
    def _setup_window(self) -> None:
        """Configura la ventana principal."""
        self.title(f"{WINDOW_TITLE} v{get_version()}")
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

    def report_callback_exception(self, exc, val, tb):
        """Tk no muestra excepciones en apps sin consola; las registramos en archivo."""
        if val is not None:
            log_exception(val, context="Tkinter/CustomTkinter callback")
        super().report_callback_exception(exc, val, tb)
    
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

        # === Activación por código (oculta hasta que haga falta) ===
        self._create_activation_form()
    
    def _create_header(self) -> None:
        """Crea el encabezado con título."""
        self.header_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.header_frame.pack(fill="x", pady=(0, 15))
        header_frame = self.header_frame
        
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

    def _create_activation_form(self) -> None:
        """Formulario de código. No se muestra hasta que la instalación no tenga credencial."""
        self.activation_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.activation_entry = ctk.CTkEntry(
            self.activation_frame,
            placeholder_text="Código de activación",
            font=ctk.CTkFont(size=14),
            height=40,
        )
        self.activation_entry.pack(fill="x", pady=(0, 8))
        self.activation_entry.bind("<Return>", lambda _event: self._on_activate_clicked())
        self.activation_error = ctk.CTkLabel(
            self.activation_frame,
            text="",
            font=ctk.CTkFont(size=12),
            text_color=THEME_WARNING,
            wraplength=440,
            justify="left",
        )
        self.activation_error.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(self.activation_frame, fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=1)
        self.activate_button = ctk.CTkButton(
            row,
            text="Activar",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME_PRIMARY,
            hover_color="#1557b0",
            command=self._on_activate_clicked,
            width=140,
            height=40,
            corner_radius=8,
        )
        self.activate_button.grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.skip_activation_button = ctk.CTkButton(
            row,
            text="Continuar sin activar",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            text_color=("gray70", "gray30"),
            hover_color=("gray20", "gray80"),
            command=self._on_continue_after_check_fail,
            width=200,
            height=40,
            corner_radius=8,
        )
        self.skip_activation_button.grid(row=0, column=1, sticky="e")

    def _hide_activation_ui(self) -> None:
        if hasattr(self, "activation_frame"):
            try:
                self.activation_frame.pack_forget()
            except Exception:
                pass

    def _show_activation_state(self, error: Optional[str] = None) -> None:
        """Pide el código de venta. El código no se guarda ni se escribe en el registro."""
        self._hide_check_failed_ui()
        self._hide_activation_ui()
        if hasattr(self, "version_frame"):
            self.version_frame.pack_forget()
        if hasattr(self, "changelog_frame"):
            self.changelog_frame.pack_forget()
        if hasattr(self, "button_frame"):
            self.button_frame.pack_forget()
        if hasattr(self, "progress_frame"):
            try:
                self.progress_bar.stop()
            except Exception:
                pass
            self.progress_frame.pack_forget()

        self.title_label.configure(
            text="Activar instalación",
            text_color=("gray10", "gray90"),
        )
        self.subtitle_label.configure(
            text="Ingresá el código que te dio tu proveedor",
            text_color="gray",
        )
        self.activation_error.configure(text=error or "")
        self.activate_button.configure(state="normal", text="Activar")
        self.activation_frame.pack(fill="x", pady=(0, 10), after=self.header_frame)
        self.activation_entry.focus_set()

    def _on_activate_clicked(self) -> None:
        if self._is_activating or self._is_updating:
            return
        code = self.activation_entry.get().strip()
        if not code:
            self.activation_error.configure(text="Ingresá el código de activación.")
            return
        self._is_activating = True
        self.activate_button.configure(state="disabled", text="Activando...")
        self.activation_error.configure(text="")
        thread = threading.Thread(target=self._activate_worker, args=(code,), daemon=True)
        thread.start()

    def _activate_worker(self, code: str) -> None:
        try:
            self.updater.activate(code)
        except UpdateError as exc:
            message = user_message_for_activation(exc)
            self.after(0, lambda msg=message: self._on_activation_failed(msg))
            return
        except Exception as exc:
            log_exception(exc, context="activate")
            self.after(
                0,
                lambda: self._on_activation_failed(
                    "No se pudo activar por un error inesperado.\n\n"
                    "Podés reintentar o continuar con la versión instalada."
                ),
            )
            return
        self.after(0, self._on_activation_success)

    def _on_activation_failed(self, message: str) -> None:
        if not self.winfo_exists():
            return
        self._is_activating = False
        self._show_activation_state(error=message)

    def _on_activation_success(self) -> None:
        if not self.winfo_exists():
            return
        self._is_activating = False
        self.activation_entry.delete(0, "end")
        self._hide_activation_ui()
        self._is_checking = True
        self._show_checking_state()
        if self.check_callback:
            self.after(200, self.check_callback)
    
    def _show_checking_state(self) -> None:
        """Muestra el estado de búsqueda de actualizaciones."""
        self._hide_activation_ui()
        self.title_label.configure(
            text="🔍 Buscando Actualizaciones...",
            text_color=("gray10", "gray90"),
        )
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
    
    def update_with_result(
        self,
        update_info: Optional[UpdateInfo],
        check_failed_message: Optional[str] = None,
        check_failed_title: Optional[str] = None,
        show_activation: bool = False,
    ) -> None:
        """
        Actualiza la UI con el resultado de la búsqueda de actualizaciones.
        
        Args:
            update_info: Información de actualización o None si no hay actualización
            check_failed_message: Si la verificación falló (red, etc.), texto para el usuario
            check_failed_title: Título alternativo cuando el fallo no es de red
            show_activation: Volver al formulario de código (identificación rechazada)
        """
        self.update_info = update_info
        self._is_checking = False
        
        # Detener barra de progreso
        if hasattr(self, 'progress_bar'):
            self.progress_bar.stop()
            self.progress_frame.pack_forget()

        if show_activation:
            self._show_activation_state(error=check_failed_message)
            return
        
        if update_info:
            # Hay actualización disponible
            self._hide_activation_ui()
            self._hide_check_failed_ui()
            self.title_label.configure(text="🔄 Actualización Disponible", text_color=("gray10", "gray90"))
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
        elif check_failed_message:
            self._show_check_failed_state(check_failed_message, title=check_failed_title)
        else:
            self._show_up_to_date_state()
    
    def _hide_check_failed_ui(self) -> None:
        """Oculta el bloque de mensaje cuando falló la verificación (p. ej. al reintentar)."""
        if hasattr(self, "check_fail_frame"):
            try:
                self.check_fail_frame.pack_forget()
            except Exception:
                pass
    
    def _ensure_check_fail_widgets(self) -> None:
        """Crea una sola vez el área de texto y botones para fallo de verificación."""
        if hasattr(self, "check_fail_frame"):
            return
        self.check_fail_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.check_fail_text = ctk.CTkTextbox(
            self.check_fail_frame,
            height=150,
            font=ctk.CTkFont(size=12),
            wrap="word",
        )
        self.check_fail_text.pack(fill="x", pady=(0, 12))
        row = ctk.CTkFrame(self.check_fail_frame, fg_color="transparent")
        row.pack(fill="x")
        row.grid_columnconfigure(0, weight=1)
        self.retry_check_button = ctk.CTkButton(
            row,
            text="Reintentar",
            font=ctk.CTkFont(size=13),
            fg_color="transparent",
            border_width=1,
            text_color=("gray70", "gray30"),
            hover_color=("gray20", "gray80"),
            command=self._on_retry_check_clicked,
            width=140,
            height=40,
            corner_radius=8,
        )
        self.retry_check_button.grid(row=0, column=0, padx=(0, 10), sticky="w")
        self.continue_after_fail_button = ctk.CTkButton(
            row,
            text="Continuar sin actualizar",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=THEME_PRIMARY,
            hover_color="#1557b0",
            command=self._on_continue_after_check_fail,
            width=200,
            height=40,
            corner_radius=8,
        )
        self.continue_after_fail_button.grid(row=0, column=1, sticky="e")
    
    def _show_check_failed_state(self, message: str, title: Optional[str] = None) -> None:
        """Muestra aviso cuando no se pudo verificar actualizaciones (red, licencia, etc.)."""
        self._hide_activation_ui()
        self._hide_check_failed_ui()
        if hasattr(self, "version_frame"):
            self.version_frame.pack_forget()
        if hasattr(self, "changelog_frame"):
            self.changelog_frame.pack_forget()
        if hasattr(self, "button_frame"):
            self.button_frame.pack_forget()
        
        self.title_label.configure(
            text=title or "No se pudo verificar actualizaciones",
            text_color=THEME_WARNING,
        )
        self.subtitle_label.configure(text="")
        
        self._ensure_check_fail_widgets()
        self.check_fail_text.configure(state="normal")
        self.check_fail_text.delete("1.0", "end")
        self.check_fail_text.insert("1.0", message)
        self.check_fail_text.configure(state="disabled")
        self.check_fail_frame.pack(fill="x", pady=(0, 10), after=self.header_frame)
    
    def _on_retry_check_clicked(self) -> None:
        """Vuelve a ejecutar la búsqueda de actualizaciones."""
        if self._is_updating:
            return
        self._hide_check_failed_ui()
        self._is_checking = True
        self._show_checking_state()
        if self.check_callback:
            self.after(400, self.check_callback)
    
    def _show_up_to_date_state(self) -> None:
        """Muestra la ventana unos segundos antes de abrir el POS."""
        self._hide_activation_ui()
        self._hide_check_failed_ui()
        self.title_label.configure(
            text="No hay actualizaciones",
            text_color=("gray10", "gray90"),
        )
        if self.has_backups_available:
            subtitle = "Tenés unos segundos para restaurar la versión anterior"
        else:
            subtitle = "El Sistema POS se abrirá en unos segundos"
        self.subtitle_label.configure(text=subtitle, text_color="gray")

        if hasattr(self, "changelog_frame"):
            self.changelog_frame.pack_forget()
        if hasattr(self, "version_frame"):
            self.version_frame.pack(fill="x", pady=(0, 15))
            self._update_version_info()

        self.progress_frame.pack(fill="x", pady=(0, 15))
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        self.status_label.configure(
            text="Redirigiendo al Sistema POS…",
            text_color=("gray10", "gray90"),
        )

        if hasattr(self, "skip_button"):
            self.skip_button.grid_remove()
        if hasattr(self, "update_button"):
            self.update_button.grid_remove()
        if hasattr(self, "restore_button"):
            self.restore_button.grid(
                row=0, column=0, padx=(0, 10), pady=(10, 10), sticky="w"
            )
            self.button_frame.pack(fill="x", pady=(10, 10))
        elif hasattr(self, "button_frame"):
            self.button_frame.pack_forget()

        self._start_redirect_countdown()

    def _start_redirect_countdown(self) -> None:
        """Llena la barra durante UP_TO_DATE_REDIRECT_MS y después abre el POS."""
        self._redirect_cancelled = False
        self._redirect_started = time.monotonic()
        self._tick_redirect()

    def _tick_redirect(self) -> None:
        if self._redirect_cancelled or not self.winfo_exists():
            return
        duration_s = UP_TO_DATE_REDIRECT_MS / 1000
        elapsed = time.monotonic() - self._redirect_started
        fraction = min(1.0, elapsed / duration_s)
        self.progress_bar.set(fraction)
        if fraction >= 1.0:
            self._complete_redirect()
            return
        remaining_s = max(1, math.ceil(duration_s - elapsed))
        self.progress_label.configure(text=f"{remaining_s} s")
        self._redirect_after_id = self.after(50, self._tick_redirect)

    def _complete_redirect(self) -> None:
        self._redirect_after_id = None
        self.launch_pos_on_close = True
        self.destroy()

    def _cancel_redirect(self) -> None:
        self._redirect_cancelled = True
        after_id = self._redirect_after_id
        self._redirect_after_id = None
        if after_id is not None:
            try:
                self.after_cancel(after_id)
            except Exception:
                pass

    def _request_close(self, launch_pos: bool) -> None:
        """Cierra la ventana. launch_pos indica si después hay que abrir el POS."""
        self._cancel_redirect()
        self.launch_pos_on_close = launch_pos
        self.destroy()

    def _on_continue_after_check_fail(self) -> None:
        """Cierra el launcher y deja que el flujo principal abra la app instalada."""
        if self._is_updating:
            return
        self._request_close(True)
    
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
        self._request_close(True)
    
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
        self.changelog_title = ctk.CTkLabel(
            self.changelog_frame,
            text="📋 Notas de la versión:",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        )
        self.changelog_title.pack(fill="x")
        
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
                except BackupError as exc:
                    log_exception(exc, context="create_backup antes de descargar")
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
            except BackupError as exc:
                log_exception(exc, context="create_backup antes de instalar")

            # Aplicar actualización
            self.updater.apply_update()

            # Éxito
            self.after(0, self._on_update_success)
        
        except Exception as exc:
            log_exception(exc, context="_download_and_apply")
            if backup_created:
                try:
                    self.backup_manager.downgrade()
                except Exception as restore_exc:
                    log_exception(restore_exc, context="downgrade tras fallo de actualización")
            error_msg = f"{exc}\n\nRegistro: {get_log_file_path()}"
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
        self._request_close(True)
    
    def _on_update_error(self, error_message: str) -> None:
        """
        Maneja error durante la actualización.
        
        Args:
            error_message: Mensaje de error
        """
        self.progress_bar.stop()
        self.progress_bar.configure(mode="determinate")
        self.progress_bar.set(0)
        
        self.title_label.configure(text="No se pudo actualizar", text_color=THEME_ERROR)
        self.subtitle_label.configure(text="Detalle del fallo", text_color=THEME_ERROR)
        self.status_label.configure(
            text="❌ Error",
            text_color=THEME_ERROR,
        )
        self.progress_label.configure(text="")
        
        # El mensaje estaba en la barra de progreso; al ocultarla desaparecía.
        self.progress_frame.pack_forget()
        if hasattr(self, "changelog_title"):
            self.changelog_title.configure(text="Error:")
        if hasattr(self, 'changelog_text'):
            self.changelog_text.master.pack(fill="both", expand=True, pady=(0, 15))
            self.changelog_text.configure(state="normal")
            self.changelog_text.delete("1.0", "end")
            self.changelog_text.insert("1.0", error_message)
            self.changelog_text.configure(state="disabled")
        
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

        self._request_close(True)
    
    def _on_restore_clicked(self) -> None:
        """Maneja clic en botón Restaurar versión anterior."""
        if self._is_updating:
            return

        self._cancel_redirect()
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
        
        except BackupError as exc:
            log_exception(exc, context="_restore_backup")
            error_msg = f"{exc}\n\nRegistro: {get_log_file_path()}"
            self.after(0, lambda msg=error_msg: self._on_restore_error(msg))
        except Exception as exc:
            log_exception(exc, context="_restore_backup")
            error_msg = f"{exc}\n\nRegistro: {get_log_file_path()}"
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
        """Finaliza la restauración y cierra. El POS ya se inició en el éxito."""
        self._request_close(False)
    
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
            text="❌ Error",
            text_color=THEME_ERROR,
        )
        self.progress_label.configure(text="")
        self._is_updating = False

        if self.update_info is None:
            self.status_label.configure(text=f"❌ Error: {error_message}")
            if hasattr(self, "changelog_frame"):
                self.changelog_frame.pack_forget()
            self.progress_frame.pack(fill="x", pady=(0, 15))
            if hasattr(self, "skip_button"):
                self.skip_button.grid_remove()
            if hasattr(self, "update_button"):
                self.update_button.grid_remove()
            if hasattr(self, "restore_button"):
                self.restore_button.grid(
                    row=0, column=0, padx=(0, 10), pady=(10, 10), sticky="w"
                )
                self.button_frame.pack(fill="x", pady=(10, 10))
            self._start_redirect_countdown()
            return

        # Ocultar progreso y mostrar el error en el recuadro visible
        self.progress_frame.pack_forget()
        if hasattr(self, "changelog_title"):
            self.changelog_title.configure(text="Error:")
        if hasattr(self, 'changelog_text'):
            self.changelog_text.master.pack(fill="both", expand=True, pady=(0, 15))
            self.changelog_text.configure(state="normal")
            self.changelog_text.delete("1.0", "end")
            self.changelog_text.insert("1.0", error_message)
            self.changelog_text.configure(state="disabled")

        # Volver a mostrar y rehabilitar botones
        column = 0
        if hasattr(self, 'skip_button'):
            self.skip_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        if hasattr(self, 'restore_button'):
            self.restore_button.grid(row=0, column=column, padx=(0, 10), pady=(10, 10), sticky="w")
            column += 1
        self.update_button.grid(row=0, column=2, padx=0, pady=(10, 10), sticky="e")
    
    def _on_close(self) -> None:
        """Cierra el launcher sin abrir el POS."""
        if self._is_updating:
            # No permitir cerrar durante actualización
            return

        self._request_close(False)
