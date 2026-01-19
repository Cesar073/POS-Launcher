import os
import sys
import requests
from pathlib import Path
# Raíz del proyecto (donde están pos_gui, pos_core, repository)
# En CI: workspace/
# En desarrollo local: ajustar según estructura
PROJECT_ROOT = Path(__file__).parent.parent.parent / "POS"
print(PROJECT_ROOT)
# Intentar importar versión desde el módulo, sino lanza excepción
sys.path.insert(0, str(PROJECT_ROOT))
from pos_core.core.resources.version import __version__

GITHUB_API = "https://api.github.com"
OWNER = "Cesar073"
REPO = "POS-Releases"
DEST_DIR = Path("downloads")
VERSION = __version__

SO = "Windows"
# SO = "Raspbian"
# SO = "Linux"

if SO == "Windows":
    ARTIFACT_NAME_APP = f"POS-Windows-v{VERSION}"
    ARTIFACT_NAME_LAUNCHER = f"POS-Launcher-Windows-v{VERSION}"
    ARTIFACT_NAME_CHECKSUMS = "checksums-windows.txt"
elif SO == "Raspbian":
    ARTIFACT_NAME_APP = f"POS-Raspbian-v{VERSION}"
    ARTIFACT_NAME_LAUNCHER = f"POS-Launcher-Raspbian-v{VERSION}"
    ARTIFACT_NAME_CHECKSUMS = "checksums-raspbian.txt"
elif SO == "Linux":
    ARTIFACT_NAME_APP = f"POS-Linux-v{VERSION}"
    ARTIFACT_NAME_LAUNCHER = f"POS-Launcher-Linux-v{VERSION}"
    ARTIFACT_NAME_CHECKSUMS = "checksums-linux.txt"
else:
    raise ValueError(f"SO '{SO}' no soportado")


def get_headers(binary: bool = False) -> dict:
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN no definido")

    headers = {
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    headers["Accept"] = (
        "application/octet-stream"
        if binary
        else "application/vnd.github+json"
    )

    return headers


def get_latest_release():
    """Obtiene el release más reciente."""
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO}/releases/latest"
    r = requests.get(url, headers=get_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def get_workflow_artifacts():
    """Obtiene los artifacts del último workflow exitoso."""
    # Primero obtener las últimas ejecuciones del workflow
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO}/actions/runs"
    params = {"status": "completed", "per_page": 10}
    r = requests.get(url, headers=get_headers(), params=params, timeout=10)
    r.raise_for_status()
    runs = r.json()["workflow_runs"]

    # Filtrar por workflow "Build and Release POS" y status success
    build_workflow = None
    for run in runs:
        if run["name"] == "Build and Release POS" and run["conclusion"] == "success":
            build_workflow = run
            break

    if not build_workflow:
        raise RuntimeError("No se encontró una ejecución exitosa del workflow 'Build and Release POS'")

    # Obtener artifacts de esa ejecución
    run_id = build_workflow["id"]
    url = f"{GITHUB_API}/repos/{OWNER}/{REPO}/actions/runs/{run_id}/artifacts"
    r = requests.get(url, headers=get_headers(), timeout=10)
    r.raise_for_status()
    return r.json()["artifacts"]


def find_artifact(artifacts: list, name: str) -> dict:
    """Encuentra un artifact por nombre."""
    for artifact in artifacts:
        if artifact["name"] == name:
            return artifact
    raise RuntimeError(f"Artifact '{name}' no encontrado")


def download_artifact(artifact: dict):
    """Descarga un artifact completo (ZIP)."""
    DEST_DIR.mkdir(exist_ok=True)

    output = DEST_DIR / f"{artifact['name']}.zip"
    url = artifact["archive_download_url"]

    with requests.get(
        url,
        headers=get_headers(binary=True),
        stream=True,
        timeout=30,
    ) as r:
        r.raise_for_status()
        with open(output, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    return output


def find_asset(release: dict, name: str) -> dict:
    for asset in release["assets"]:
        if asset["name"] == name:
            return asset
    raise RuntimeError(f"Asset '{name}' no encontrado en el release")


def download_asset(asset: dict):
    DEST_DIR.mkdir(exist_ok=True)

    output = DEST_DIR / asset["name"]
    url = asset["url"]

    with requests.get(
        url,
        headers=get_headers(binary=True),
        stream=True,
        timeout=30,
    ) as r:
        r.raise_for_status()
        with open(output, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

    return output


def main(artifact_name: str, is_app: bool = True):
    try:
        # Intentar descargar desde releases primero
        release = get_latest_release()
        extension = ""
        if is_app:
            extension = ".zip" if SO == "Windows" else ".tar.gz"
        asset = find_asset(release, f"{artifact_name}{extension}")
        path = download_asset(asset)
        print(f"Descargado desde releases: {path}")
        print(f"Versión: {release['tag_name']}")
    except Exception as e:
        print(f"No se pudo descargar desde releases: {e}")
        print("Intentando descargar desde artifacts...")

        # Si no hay releases, intentar desde artifacts
        artifacts = get_workflow_artifacts()
        artifact = find_artifact(artifacts, artifact_name)
        path = download_artifact(artifact)
        print(f"Descargado desde artifacts: {path}")
        print("Nota: Los artifacts son temporales (30 días)")


if __name__ == "__main__":
    try:
        main(ARTIFACT_NAME_APP, is_app=True)  # La aplicación tiene extensión .tar.gz
        main(ARTIFACT_NAME_LAUNCHER, is_app=False)  # El launcher no tiene extensión en el asset
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
