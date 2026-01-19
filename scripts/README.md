# POS-Releases

Repositorio de CI/CD para compilar y distribuir el Sistema POS.

## 📋 Descripción

Este repositorio contiene:
- **GitHub Actions workflows** para compilar automáticamente la aplicación
- **Scripts de compilación** con Nuitka
- **Sistema de actualización** (launcher) que verifica y aplica actualizaciones
- **Script de subida** a Google Drive

## 🚀 Cómo crear un Release

### Desde GitHub Actions (recomendado)

1. Ve a la pestaña **Actions** del repositorio
2. Selecciona **"Build and Release POS"**
3. Click en **"Run workflow"**
4. Completa los campos:
   - **Version**: Número de versión (ej: `0.1.0`)
   - **Changelog**: Descripción de los cambios
   - **Build Launcher**: Marcar si necesitas recompilar el launcher
5. Click en **"Run workflow"**

El workflow:
- Clona los repositorios de desarrollo
- Compila con Nuitka
- Calcula checksums SHA256
- Sube a Google Drive
- Actualiza `version.json`

### Manual (desarrollo local)

```bash
# 1. Clonar este repo
git clone https://github.com/Cesar073/POS-Releases.git
cd POS-Releases

# 2. Clonar repos de desarrollo
git clone https://github.com/Cesar073/pos_gui.git src/pos_gui
git clone https://github.com/Cesar073/Point_of_Sale.git src/pos_core_repo
git clone https://github.com/Cesar073/pos_repository.git src/pos_repository

# 3. Organizar estructura
# (ver workflow para la estructura exacta)

# 4. Compilar
python build/build.py
```

## 📁 Estructura

```
POS-Releases/
├── .github/workflows/
│   └── build-release.yml    ← GitHub Actions
├── build/
│   ├── build.py             ← Script compilación app
│   ├── build_launcher.py    ← Script compilación launcher
│   └── config.py            ← Configuración Nuitka
├── launcher/
│   ├── main.py              ← Punto de entrada launcher
│   ├── updater.py           ← Sistema de actualización
│   ├── ui.py                ← Interfaz gráfica
│   └── ...
├── scripts/
│   └── upload_to_drive.py   ← Subir a Google Drive
├── requirements.txt         ← Deps de la app
└── requirements-build.txt   ← Deps de compilación
```

## 🔐 Secrets Requeridos

Configurar en **Settings > Secrets and variables > Actions**:

| Secret | Descripción |
|--------|-------------|
| `GOOGLE_CREDENTIALS` | Contenido del JSON de la Service Account |
| `DRIVE_FOLDER_ID` | ID de la carpeta en Google Drive |

## 📦 Repositorios de Desarrollo

- **UI:** [Cesar073/pos_gui](https://github.com/Cesar073/pos_gui)
- **Core:** [Cesar073/Point_of_Sale](https://github.com/Cesar073/Point_of_Sale)
- **Repository:** [Cesar073/pos_repository](https://github.com/Cesar073/pos_repository)

## 📝 Notas

- El launcher descarga actualizaciones desde Google Drive
- Los ejecutables se compilan con Nuitka (mejor rendimiento que PyInstaller)
- Windows es la plataforma principal, Linux en desarrollo
