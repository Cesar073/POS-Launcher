# Manual de usuario

Este capítulo explica qué información sale de la computadora hacia el servidor de Efecto Dominó. El resto del manual todavía no está escrito. Cada vez que el POS o el Launcher hablen con el servidor, este capítulo tiene que decirlo en estos términos: cuándo ocurre, qué se envía y qué no.

El servidor reconoce la instalación por la credencial que quedó al activar el Launcher. Esa credencial no se muestra en pantalla.

## Launcher

### Activar la instalación

Ocurre cuando se escribe el código de activación y se confirma.

Se envía el código, un identificador de la computadora, el sistema operativo y la versión del Launcher. El servidor responde con la credencial de esa instalación. El código no se guarda en el archivo de errores.

### Buscar una actualización del POS

Ocurre cada vez que se abre el Launcher, después de mostrar la ventana.

Se envía la versión del POS que está instalada y el sistema operativo. El servidor responde si hay una versión más nueva, las notas de esa versión y si esta instalación puede actualizar.

### Avisar que se consultó una actualización

Ocurre enseguida después de esa búsqueda, sin un botón extra.

Se envía la versión del POS y el sistema operativo. Sirve para que el servidor sepa que esta instalación consultó actualizaciones. No se envía el contenido del programa ni de la base de datos.

### Consultar la licencia

Ocurre durante la búsqueda de actualizaciones, cuando la respuesta anterior no trae el estado de la licencia.

Se pregunta si la instalación está vigente y si puede actualizar. No se envían ventas ni datos del negocio.

### Descargar una versión nueva

Ocurre solo si hay una actualización y se elige descargarla.

Se baja el archivo de la versión nueva. No se sube información del POS.

### Enviar los errores del Launcher

Ocurre al cerrar el Launcher, si desde el envío anterior se agregó texto a su archivo de errores.

Se envía la cuenta de Windows, la dirección IP local de la computadora, la versión del Launcher, la versión del POS que el Launcher pudo leer y el texto nuevo de ese archivo. El archivo queda en la computadora. No se envían los registros del POS.

El archivo está en:

`%LocalAppData%\NexoPOS\Launcher\logs\launcher_errors.log`

## POS

### Consultar si puede operar

Ocurre al abrir el POS.

Se pregunta al servidor el estado de la licencia de esta instalación. Con eso el POS decide si abre con normalidad, si muestra un aviso o si no puede operar.

### Avisar que el POS se abrió

Ocurre al abrir el POS, después de esa consulta, si hay credencial.

Se envía la versión del POS y el sistema operativo. No se envían ventas, clientes ni el contenido de los registros locales.

## Qué queda solo en la computadora

Estos archivos no se envían solos.

| Archivo | Contenido |
|---|---|
| `%LocalAppData%\NexoPOS\POS\logs\pos_AAAA-MM-DD.log` | Actividad del POS de ese día: avisos e información. No incluye errores. |
| `%LocalAppData%\NexoPOS\POS\logs\pos_error_AAAA-MM-DD.log` | Errores del POS de ese día. |
| `%LocalAppData%\NexoPOS\POS\startup_error.log` | Errores de arranque del POS, cuando ni siquiera llegó a abrir. |
| `%LocalAppData%\NexoPOS\POS\startup_error.txt` | El mismo tipo de fallo de arranque, solo si no se pudo usar el registro normal. |

El registro de actividad del día se podrá enviar a mano desde el POS. Esa acción todavía no está en el programa. Hasta entonces ese archivo no sale de la computadora.
