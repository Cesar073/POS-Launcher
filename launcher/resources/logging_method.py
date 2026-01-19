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
                    args_str = "\n    ".join([f"{k}: {v}" for k, v in args_dict.items()])
                    
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