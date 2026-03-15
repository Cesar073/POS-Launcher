# Windows Defender: Program:Win32/Contebrew.A!ml (falso positivo)

## ¿Qué está detectando Windows Defender?

**No es un virus real.** Es una **detección heurística** (el sufijo `!ml` indica *machine learning*). Defender no tiene la firma de un malware concreto; marca el ejecutable porque su **comportamiento y estructura** se parecen a patrones que suele usar malware:

1. **Ejecutable empaquetado (onefile)**  
   Nuitka con `--onefile` genera un .exe que “desempaqueta” código en tiempo de ejecución. Ese patrón es común en droppers y loaders, y los antivirus lo vigilan.

2. **Descarga de archivos desde internet**  
   El launcher descarga actualizaciones desde GitHub. Los programas que descargan y luego ejecutan otros archivos son un patrón típico de malware.

3. **Escritura en AppData y ejecución de otro .exe**  
   El launcher escribe en `%LOCALAPPDATA%\POS` y lanza `POS.exe`. Eso se parece a instaladores/launchers maliciosos.

4. **Ejecutable sin consola (GUI only)**  
   Compilar con `--windows-console-mode=disable` suele aumentar falsos positivos en Nuitka y otros compiladores.

Referencia de Microsoft: [Program:Win32/Contebrew.A!ml](https://www.microsoft.com/en-us/wdsi/threats/malware-encyclopedia-description?name=Program%3AWin32%2FContebrew.A!ml&threatid=251873).

---

## Qué puedes hacer (en orden recomendado)

### 1. Firmar el ejecutable (más efectivo)

Firmar el .exe con un **certificado de firma de código** (EV o estándar) reduce mucho los falsos positivos, porque Windows confía en editores conocidos.

- **Certificado estándar**: compra en DigiCert, Sectigo, etc.  
- **Certificado EV (Extended Validation)**: más caro pero suele dar confianza inmediata en SmartScreen y antivirus.

Después de compilar, firma con `signtool` (Windows SDK) o desde tu script de build.

### 2. Reportar el falso positivo a Microsoft

Puedes enviar tu .exe para que lo analicen y lo marquen como seguro:

1. Entra en [Microsoft Security Intelligence - Submit a file](https://www.microsoft.com/en-us/wdsi/filesubmission).
2. Elige “Submit a file for analysis”.
3. Sube el ejecutable compilado (ej. `Launcher_Windows.exe`).
4. Indica que es un **false positive** y que es tu aplicación legítima (launcher/actualizador).

Suele tardar unos días; a veces añaden una excepción o ajustan la heurística.

### 3. Probar compilación en modo onedir (sin onefile)

Algunos falsos positivos bajan si en lugar de un solo .exe empaquetado generas una **carpeta** con el .exe y las DLLs (modo “onedir” en Nuitka).

En el script de build puedes usar:

```bash
python build/build_launcher.py --onedir
```

(Requiere que el script soporte la opción `--onedir`; ver `build/build_launcher.py`.)

La distribución será una carpeta en lugar de un único .exe.

### 4. Excepción local en Windows Defender (solo para desarrollo/pruebas)

Para poder ejecutar tu propio software en tu máquina sin que Defender lo borre:

- **Windows Security** → **Virus & threat protection** → **Manage settings** → **Exclusions** → añade la carpeta `dist` o el .exe del launcher.

No es una solución para entregar a usuarios finales; para eso lo correcto es firma + envío del falso positivo a Microsoft.

---

## Resumen

| Acción                         | Uso recomendado                          |
|--------------------------------|------------------------------------------|
| Firma de código                | Distribución a usuarios (muy recomendado) |
| Enviar falso positivo a Microsoft | Una vez por versión/build importante  |
| Build con `--onedir`          | Probar si baja la detección              |
| Exclusión en Defender         | Solo en tu PC para desarrollar/probar     |

Tu código es legítimo; la detección se debe al tipo de programa (launcher que descarga y ejecuta) y al formato del ejecutable (onefile + sin consola), no a malware real.
