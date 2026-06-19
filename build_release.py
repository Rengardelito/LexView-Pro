"""
build_release.py — Empaqueta release completo para GitHub.

Uso:
    python build_release.py 2.3.9

Genera:
    dist/lexview-update-2.3.9.zip
    dist/lexview-update-2.3.9.zip.sha256

Incluye:
    - código fuente actualizable
    - templates/static/helpers/bots/database
    - version.txt
    - LexViewPro.exe si existe
"""

import sys
import hashlib
import zipfile
from pathlib import Path

UPDATABLE_FILES = [
    "app.py",
    "config.py",
    "launcher.py",
    "version.txt",
]

UPDATABLE_DIRS = [
    "bots",
    "helpers",
    "templates",
    "static",
    "database",
]

EXE_CANDIDATES = [
    "LexViewPro.exe",
    "dist/LexViewPro/LexViewPro.exe",
]

EXCLUDE_EXTENSIONS = {".pyc", ".pyo", ".DS_Store", ".db", ".sqlite", ".sqlite3", ".sqbpro"}
EXCLUDE_DIRS = {
    "__pycache__",
    ".git",
    ".pytest_cache",
    "output",
    "data",
    "expedientes_clientes",
    "venv",
}


def debe_excluir(path: Path) -> bool:
    if path.suffix.lower() in EXCLUDE_EXTENSIONS:
        return True

    if any(part in EXCLUDE_DIRS for part in path.parts):
        return True

    return False


def agregar_archivo(zf: zipfile.ZipFile, src: Path, arcname: str):
    if not src.exists():
        print(f"  ⚠ No encontrado: {src}")
        return False

    zf.write(src, arcname)
    print(f"  + {arcname}")
    return True


def build_zip(version: str, project_root: Path) -> Path:
    dist_dir = project_root / "dist"
    dist_dir.mkdir(exist_ok=True)

    zip_name = f"lexview-update-{version}.zip"
    zip_path = dist_dir / zip_name

    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:

        # Archivos sueltos
        for filename in UPDATABLE_FILES:
            src = project_root / filename

            if filename == "version.txt":
                zf.writestr("update/version.txt", version.encode("utf-8"))
                print(f"  + update/version.txt ({version})")
                continue

            agregar_archivo(zf, src, f"update/{filename}")

        # Carpetas
        for dir_name in UPDATABLE_DIRS:
            src_dir = project_root / dir_name

            if not src_dir.exists():
                print(f"  ⚠ Carpeta no encontrada: {dir_name}/")
                continue

            for file_path in src_dir.rglob("*"):
                if file_path.is_dir():
                    continue

                rel = file_path.relative_to(project_root)

                if debe_excluir(rel):
                    continue

                zf.write(file_path, f"update/{rel}")
                print(f"  + update/{rel}")

        # EXE
        exe_agregado = False

        for exe_rel in EXE_CANDIDATES:
            exe_path = project_root / exe_rel

            if exe_path.exists():
                # Va dentro de update/ para que el updater pueda reemplazarlo.
                zf.write(exe_path, "update/LexViewPro.exe")
                print(f"  + update/LexViewPro.exe ← {exe_rel}")
                exe_agregado = True
                break

        if not exe_agregado:
            print("  ⚠ No se encontró LexViewPro.exe. El zip se generó sin EXE.")

    print(f"\nZip generado: {zip_path} ({zip_path.stat().st_size // 1024} KB)")
    return zip_path


def compute_sha256(zip_path: Path) -> str:
    sha256 = hashlib.sha256()

    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)

    return sha256.hexdigest()


def write_sha256_file(zip_path: Path, digest: str):
    sha_path = zip_path.with_suffix(".zip.sha256")
    sha_path.write_text(f"{digest}  {zip_path.name}\n", encoding="utf-8")

    print(f"SHA256: {digest}")
    print(f"Archivo: {sha_path}")


def main():
    if len(sys.argv) < 2:
        print("Uso: python build_release.py <version>")
        print("Ejemplo: python build_release.py 2.3.9")
        sys.exit(1)

    version = sys.argv[1].lstrip("v")
    project_root = Path(__file__).parent.resolve()

    print(f"\n{'=' * 50}")
    print(f"  LexView Pro — Build Release v{version}")
    print(f"{'=' * 50}\n")
    print("Empaquetando archivos...")

    zip_path = build_zip(version, project_root)
    digest = compute_sha256(zip_path)
    write_sha256_file(zip_path, digest)

    print(f"\n{'=' * 50}")
    print("  Próximos pasos:")
    print(f"{'=' * 50}")
    print(f"1. git tag v{version} && git push origin v{version}")
    print(f"2. Subir {zip_path.name} a GitHub Releases (tag v{version})")
    print(f"3. Actualizar endpoint del VPS con:")
    print(f'   version = "{version}"')
    print(f'   sha256  = "{digest}"')
    print(f"4. sudo systemctl restart lexview")
    print(f"\nSHA256:")
    print(digest)


if __name__ == "__main__":
    main()