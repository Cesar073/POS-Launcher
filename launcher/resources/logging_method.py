import functools
import inspect
from datetime import datetime


class MethodLogger:
    """Clase singleton que maneja el logging de métodos y funciones con indentación para mostrar contexto.
    
    Uso con clases:
        logger = MethodLogger()
        
        @logger.log_class
        class MiClase:
            def mi_metodo(self):
                pass
    
    Uso con funciones:
        @logger.log_function
        def mi_funcion(a, b):
            return a + b
    
    La indentación aumenta con cada llamada anidada, permitiendo ver:
        ┌─ INPUT: [ClaseA][metodo1]
        │   ┌─ INPUT: [mi_funcion]
        │   └─ OUTPUT: [mi_funcion]
        └─ OUTPUT: [ClaseA][metodo1]
    """
    
    _instance = None
    _initialized = False  # Atributo de clase para el patrón singleton
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self.__class__._initialized = True
        
        # Configuración
        self.indent_level = 0
        self.indent_size = 4  # Espacios por nivel
        self.indent_char = " "
        
        # Filtros/Triggers (si están vacíos, loguea todo)
        # Cuando un método trigger se ejecuta, loguea TODO hasta que ese método termine
        self.trigger_functions = ["_on_load_sale_button"]  # Lista de nombres de funciones que activan logging
        self.trigger_classes = []    # Lista de nombres de clases que activan logging
        
        # Estado de activación
        self._has_triggers = False   # True si hay triggers configurados
        self._trigger_depth = 0      # Contador de triggers activos anidados
        self._should_log = True      # Estado actual de logging
        
        # Símbolos para visualización del árbol
        self.symbols = {
            'input_start': '┌─',
            'output_end': '└─',
            'continue': '│ ',
            'arrow': '→',
        }
    
    def _get_indent(self) -> str:
        """Retorna la indentación actual."""
        base_text = "│   "
        text = base_text * self.indent_level
        return text
    
    def _get_prefix(self, is_input: bool = True) -> str:
        """Retorna el prefijo con símbolo de árbol."""
        indent = self._get_indent()
        symbol = self.symbols['input_start'] if is_input else self.symbols['output_end']
        return f"{indent}{symbol}"
    
    def _print_log(self, message: str, is_input: bool = True):
        """Imprime un mensaje con la indentación y formato correctos."""
        prefix = self._get_prefix(is_input)
        # Agregar continuación para líneas adicionales
        continuation = self._get_indent() + self.symbols['continue'] + "  "
        lines = message.split('\n')
        print(f"{prefix} {lines[0]}")
        if not is_input:
            continuation = self._get_indent() + "   "
        for line in lines[1:]:
            print(f"{continuation}{line}")
    
    def set_triggers(self, functions: list = None, classes: list = None):
        """Configura los triggers de logging.
        
        Cuando un método/clase trigger se ejecuta, se loguea TODO el árbol
        de ejecución hasta que ese método termine (incluyendo llamadas anidadas).
        
        Args:
            functions: Lista de nombres de funciones que activan el logging
            classes: Lista de nombres de clases que activan el logging
            
        Ejemplo:
            logger.set_triggers(functions=["crear_venta"])
            # Ahora cuando "crear_venta" se ejecute, verás todo el árbol:
            # ┌─ INPUT: [Cashier][crear_venta]
            # │   ┌─ INPUT: [Repository][save]
            # │   └─ OUTPUT: [Repository][save]
            # └─ OUTPUT: [Cashier][crear_venta]
        """
        self.trigger_functions = functions or []
        self.trigger_classes = classes or []
        self._has_triggers = bool(self.trigger_functions or self.trigger_classes)
        self._trigger_depth = 0
        self._should_log = not self._has_triggers  # Si hay triggers, no logueamos hasta que uno se active
    
    def clear_triggers(self):
        """Limpia todos los triggers, loguea todo."""
        self.trigger_functions = []
        self.trigger_classes = []
        self._has_triggers = False
        self._trigger_depth = 0
        self._should_log = True
    
    # Alias para compatibilidad
    set_filters = set_triggers
    clear_filters = clear_triggers
    
    def _is_trigger(self, class_name: str = None, method_name: str = None, function_name: str = None) -> bool:
        """Determina si este método/función es un trigger."""
        if not self._has_triggers:
            return False
        if function_name:
            return function_name in self.trigger_functions
        return method_name in self.trigger_functions or (class_name and class_name in self.trigger_classes)

    def _format_value(self, value, indent_level: int = 0) -> str:
        """Formatea un valor recursivamente con indentación adecuada.
        
        Args:
            value: El valor a formatear (puede ser cualquier tipo)
            indent_level: Nivel de indentación actual (para estructuras anidadas)
            
        Returns:
            String formateado con cada elemento en una línea
        """
        indent = "  " * indent_level
        next_indent = "  " * (indent_level + 1)
        
        if value is None:
            return "None"
        elif isinstance(value, (int, float, bool)):
            return str(value)
        elif isinstance(value, str):
            return value
        elif isinstance(value, dict):
            if not value:
                return "{}"
            lines = [f"{indent}{{"]  # Primera línea con indentación
            for k, v in value.items():
                formatted_value = self._format_value(v, indent_level + 1)
                # Si el valor formateado tiene múltiples líneas, necesitamos manejar la indentación
                if "\n" in formatted_value:
                    value_lines = [line for line in formatted_value.split("\n") if line.strip()]  # Filtrar líneas vacías
                    if not value_lines:
                        lines.append(f"{next_indent}{k}: {{}}")
                        continue
                    
                    # La primera línea del valor formateado tiene indentación (indent_level + 1)
                    first_line = value_lines[0].strip()
                    if first_line == "{":
                        # Dict anidado: poner { en la misma línea que el nombre del campo
                        lines.append(f"{next_indent}{k}: {{")
                        # Las líneas siguientes (campos del dict anidado) ya tienen su indentación correcta
                        for line in value_lines[1:]:
                            if line.strip():  # Solo agregar líneas no vacías
                                lines.append(line)
                    else:
                        # Otro tipo de estructura anidada (lista, etc.)
                        lines.append(f"{next_indent}{k}: {first_line}")
                        for line in value_lines[1:]:
                            if line.strip():  # Solo agregar líneas no vacías
                                lines.append(line)
                else:
                    lines.append(f"{next_indent}{k}: {formatted_value}")
            lines.append(f"{indent}}}")
            return "\n".join(lines)
        elif isinstance(value, (list, tuple)):
            if not value:
                return "[]" if isinstance(value, list) else "()"
            bracket_open = "[" if isinstance(value, list) else "("
            bracket_close = "]" if isinstance(value, list) else ")"
            lines = [bracket_open]
            for item in value:
                # Formatear el item con el nivel de indentación correcto
                # El item se formatea con indent_level + 1, pero luego lo ponemos dentro de la lista
                # que también tiene indent_level, así que necesitamos ajustar
                formatted_item = self._format_value(item, indent_level + 1)
                # Si el item formateado tiene múltiples líneas, las líneas ya tienen su indentación
                # correcta (indent_level + 1), así que las usamos tal cual
                if "\n" in formatted_item:
                    item_lines = formatted_item.split("\n")
                    for line in item_lines:
                        lines.append(line)
                else:
                    lines.append(f"{next_indent}{formatted_item}")
            lines.append(f"{indent}{bracket_close}")
            return "\n".join(lines)
        else:
            # Para otros tipos de objetos, usar su representación string
            return str(value)
    
    def simplify_list(self, msg_list: list) -> str:
        """Simplifica una lista de strings para que se pueda imprimir en un solo line."""
        return self._format_value(msg_list)
    
    def simplify_dict(self, msg_dict: dict) -> str:
        """Simplifica un diccionario para que se pueda imprimir en un solo line."""
        return self._format_value(msg_dict)
    
    def simplify_tuple(self, msg_tuple: tuple) -> str:
        """Simplifica una tupla para que se pueda imprimir en un solo line."""
        return self._format_value(msg_tuple)
    
    def simplify_logging_message(self, message) -> str:
        """Simplifica un mensaje de logging para que se pueda imprimir con formato adecuado.
        
        Cada elemento se imprime uno debajo de otro, y las estructuras anidadas
        también se muestran con indentación apropiada.
        """
        return self._format_value(message, indent_level=0)

    def log_class(self, cls):
        """Decorador que loguea los métodos de una clase cuando se ejecutan.
        
        Imprime con indentación:
        - Nombre de la clase
        - Nombre del método
        - Argumentos de entrada 
        - Valor de retorno
        - Tiempo de ejecución
        """
        logger = self  # Referencia para el closure
        
        # Obtenemos todos los métodos de la clase que no sean magic methods
        methods = [attr for attr in dir(cls) 
                   if not attr.startswith('__') and callable(getattr(cls, attr))]
        
        for method_name in methods:
            original_method = getattr(cls, method_name)
            
            def make_wrapper(orig_method, meth_name):
                @functools.wraps(orig_method)
                def wrapper(self, *args, **kwargs):
                    # Verificar si este método es un trigger
                    is_trigger = logger._is_trigger(cls.__name__, meth_name)
                    
                    # Si hay triggers configurados
                    if logger._has_triggers:
                        if is_trigger:
                            # Este método activa el logging
                            logger._trigger_depth += 1
                            logger._should_log = True
                        elif not logger._should_log:
                            # No hay trigger activo, ejecutar sin loguear
                            return orig_method(self, *args, **kwargs)
                    
                    # Obtener nombres de parámetros
                    sig = inspect.signature(orig_method)
                    params = list(sig.parameters.keys())[1:]  # Excluimos 'self'
                    
                    # Crear diccionario con argumentos
                    args_dict = dict(zip(params, args))
                    args_dict.update(kwargs)
                    
                    # Formatear cada argumento correctamente
                    args_lines = []
                    for k, v in args_dict.items():
                        formatted_value = logger.simplify_logging_message(v)
                        # Si el valor tiene múltiples líneas, necesitamos manejar la indentación correctamente
                        if "\n" in formatted_value:
                            value_lines = formatted_value.split("\n")
                            # La primera línea va con el nombre del argumento
                            args_lines.append(f"{k}: {value_lines[0]}")
                            # Las líneas siguientes necesitan indentación adicional para alinearlas
                            # con el contenido del argumento (4 espacios base)
                            for line in value_lines[1:]:
                                # Si la línea ya tiene indentación del formateo recursivo, la mantenemos
                                # pero agregamos la indentación base del argumento
                                args_lines.append(f"    {line}")
                        else:
                            args_lines.append(f"{k}: {formatted_value}")
                    
                    # Unir las líneas - cada línea ya tiene su indentación correcta
                    args_str = "\n    ".join(args_lines)
                    
                    # Log de entrada
                    input_msg = f"INPUT: [{cls.__name__}][{meth_name}]\n"
                    input_msg += f"Args:\n    {args_str}"
                    logger._print_log(input_msg, is_input=True)
                    
                    # Incrementar indentación para llamadas anidadas
                    logger.indent_level += 1
                    start_time = datetime.now()
                    
                    try:
                        # Ejecutar método
                        result = orig_method(self, *args, **kwargs)
                    except Exception:
                        # Asegurar que la indentación se decremente incluso con excepciones
                        logger.indent_level -= 1
                        # Si era un trigger, decrementar profundidad y desactivar si es el último
                        if logger._has_triggers and is_trigger:
                            logger._trigger_depth -= 1
                            if logger._trigger_depth == 0:
                                logger._should_log = False
                        raise
                    
                    # Decrementar indentación
                    logger.indent_level -= 1
                    
                    end_time = datetime.now()
                    duration = end_time - start_time
                    
                    # Log de salida
                    output_msg = f"OUTPUT: [{cls.__name__}][{meth_name}]\n"
                    output_msg += f"Return: {result}\n"
                    output_msg += f"Time: {duration}"
                    output_msg = logger.simplify_logging_message(output_msg)
                    logger._print_log(output_msg, is_input=False)
                    
                    # Si era un trigger, decrementar profundidad
                    if logger._has_triggers and is_trigger:
                        logger._trigger_depth -= 1
                        # Solo desactivar logging cuando el último trigger termine
                        if logger._trigger_depth == 0:
                            logger._should_log = False
                    
                    return result
                return wrapper
            
            setattr(cls, method_name, make_wrapper(original_method, method_name))
        
        return cls

    def log_function(self, func):
        """Decorador que loguea una función cuando se ejecuta.
        
        Imprime con indentación:
        - Nombre de la función
        - Argumentos de entrada 
        - Valor de retorno
        - Tiempo de ejecución
        
        Uso:
            logger = MethodLogger()
            
            @logger.log_function
            def mi_funcion(a, b):
                return a + b
        
        La indentación aumenta con cada llamada anidada, permitiendo ver:
            ┌─ INPUT: [mi_funcion]
            │   ┌─ INPUT: [otra_funcion]
            │   └─ OUTPUT: [otra_funcion]
            └─ OUTPUT: [mi_funcion]
        """
        logger = self  # Referencia para el closure
        function_name = func.__name__
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Verificar si esta función es un trigger
            is_trigger = logger._is_trigger(function_name=function_name)
            
            # Si hay triggers configurados
            if logger._has_triggers:
                if is_trigger:
                    # Esta función activa el logging
                    logger._trigger_depth += 1
                    logger._should_log = True
                elif not logger._should_log:
                    # No hay trigger activo, ejecutar sin loguear
                    return func(*args, **kwargs)
            
            # Obtener nombres de parámetros
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            
            # Crear diccionario con argumentos
            args_dict = dict(zip(params, args))
            args_dict.update(kwargs)
            args_str = "\n    ".join([f"{k}: {v}" for k, v in args_dict.items()])
            
            # Log de entrada
            input_msg = f"INPUT: [{function_name}]\n"
            if args_str:
                input_msg += f"Args:\n    {args_str}"
            else:
                input_msg += "Args: (sin argumentos)"
            logger._print_log(input_msg, is_input=True)
            
            # Incrementar indentación para llamadas anidadas
            logger.indent_level += 1
            start_time = datetime.now()
            
            try:
                # Ejecutar función
                result = func(*args, **kwargs)
            except Exception:
                # Asegurar que la indentación se decremente incluso con excepciones
                logger.indent_level -= 1
                # Si era un trigger, decrementar profundidad y desactivar si es el último
                if logger._has_triggers and is_trigger:
                    logger._trigger_depth -= 1
                    if logger._trigger_depth == 0:
                        logger._should_log = False
                raise
            
            # Decrementar indentación
            logger.indent_level -= 1
            
            end_time = datetime.now()
            duration = end_time - start_time
            
            # Log de salida
            output_msg = f"OUTPUT: [{function_name}]\n"
            output_msg += f"Return: {result}\n"
            output_msg += f"Time: {duration}"
            logger._print_log(output_msg, is_input=False)
            
            # Si era un trigger, decrementar profundidad
            if logger._has_triggers and is_trigger:
                logger._trigger_depth -= 1
                # Solo desactivar logging cuando el último trigger termine
                if logger._trigger_depth == 0:
                    logger._should_log = False
            
            return result
        
        return wrapper


# Instancia global para uso conveniente
method_logger = MethodLogger()

# Alias para mantener compatibilidad con código existente
log_simple_class_methods = method_logger.log_class
log_function = method_logger.log_function