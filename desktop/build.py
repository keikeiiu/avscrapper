"""Build script: PyInstaller freeze + Electron bundle → portable .exe."""
import os
import sys
import shutil
import subprocess
import platform

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PYTHON_DIST = os.path.join(HERE, "python-dist")
IS_WIN = platform.system() == "Windows"

# Resolve node/npm/npx paths (not always in subprocess PATH on Windows)
def _find_cmd(name):
    """Find command in common install locations."""
    for base in [os.environ.get("ProgramFiles", "C:\\Program Files"),
                 os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                 os.path.expanduser("~\\AppData\\Roaming\\nvm"),
                 os.path.expanduser("~\\AppData\\Local\\Programs")]:
        for sub in [name + ".exe", name + ".cmd", os.path.join("nodejs", name + ".exe")]:
            p = os.path.join(base, sub)
            if os.path.isfile(p):
                return p
    return name  # fallback to bare name (hope it's in PATH)

NPM = _find_cmd("npm")
NPX = _find_cmd("npx")


def step(msg):
    print(f"\n=== {msg} ===")


def run(cmd, **kwargs):
    print(f"  $ {' '.join(cmd)}")
    subprocess.run(cmd, check=True, cwd=HERE, **kwargs)


def main():
    # 1. Clean
    step("Clean previous build")
    for d in [PYTHON_DIST, os.path.join(HERE, "pyinstaller-work"), os.path.join(HERE, "output")]:
        if os.path.isdir(d):
            shutil.rmtree(d)
    spec = os.path.join(HERE, "avscraper-backend.spec")
    if os.path.isfile(spec):
        os.remove(spec)

    # Clean __pycache__ from source dirs (locally-stale bytecode, not needed in CI)
    step("Clean __pycache__ from source")
    for scan_dir in [os.path.join(ROOT, "src"), os.path.join(ROOT, "web")]:
        for root, dirs, _files in os.walk(scan_dir):
            if "__pycache__" in dirs:
                shutil.rmtree(os.path.join(root, "__pycache__"))
    print("  Done")

    # 2. Generate icon
    step("Generate app icon")
    icon_dir = os.path.join(HERE, "icons")
    os.makedirs(icon_dir, exist_ok=True)
    png_path = os.path.join(icon_dir, "icon.png")
    if not os.path.isfile(png_path):
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.rounded_rectangle([4, 4, 252, 252], radius=48, fill=(15, 17, 23, 255), outline=(58, 166, 255, 180), width=3)
            draw.text((128, 90), "AV", fill=(88, 166, 255, 255), anchor="mm")
            draw.text((128, 166), "SCRAPER", fill=(63, 185, 80, 255), anchor="mm")
            img.save(png_path, "PNG")
            img.save(os.path.join(icon_dir, "icon.ico"), format="ICO", sizes=[(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)])
            print("  Icon created")
        except ImportError:
            print("  PIL not available — install pillow to generate icon")

    # 3. PyInstaller freeze
    step("PyInstaller: freeze Python backend")
    pyi_add_data = [
        f"{os.path.join(ROOT, 'web', 'templates')}{os.pathsep}web{os.sep}templates",
        f"{os.path.join(ROOT, 'web', 'static')}{os.pathsep}web{os.sep}static",
        f"{os.path.join(ROOT, 'web', 'routes')}{os.pathsep}web{os.sep}routes",
        f"{os.path.join(ROOT, 'src')}{os.pathsep}src",
        f"{os.path.join(ROOT, 'config.example.yaml')}{os.pathsep}.",
    ]
    pyi_cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onedir", "--name", "avscraper-backend",
        "--distpath", PYTHON_DIST,
        "--workpath", os.path.join(HERE, "pyinstaller-work"),
        "--specpath", HERE,
        "--hidden-import", "flask",
        "--hidden-import", "markdown",
        "--hidden-import", "yaml",
        "--hidden-import", "defusedxml",
        "--hidden-import", "playwright",
        "--hidden-import", "web.process_manager",
    ]
    for ad in pyi_add_data:
        pyi_cmd.extend(["--add-data", ad])
    pyi_cmd.append(os.path.join(ROOT, "web", "app.py"))
    run(pyi_cmd)

    # 4. Install npm deps
    step("Install npm dependencies")
    if not os.path.isdir(os.path.join(HERE, "node_modules")):
        run([NPM, "install"])

    # 5. Electron-builder (unpacked — avoids Windows code-signing symlink issues)
    step("Electron-builder: package app")
    run([NPX, "electron-builder", "--dir", "--win"])

    # electron-builder filters directories starting with _ (like _internal)
    # Copy it manually so the frozen Python runtime can find python312.dll
    step("Copy PyInstaller _internal into electron output")
    backend_out = os.path.join(HERE, "output", "win-unpacked", "resources",
                               "python-dist", "avscraper-backend")
    internal_src = os.path.join(PYTHON_DIST, "avscraper-backend", "_internal")
    internal_dst = os.path.join(backend_out, "_internal")
    if os.path.isdir(internal_dst):
        shutil.rmtree(internal_dst)
    shutil.copytree(internal_src, internal_dst)
    print(f"  Copied _internal/ to electron output")

    # Remove appdata/ if leaked from a test run (contains local paths + empty DB)
    appdata_dst = os.path.join(backend_out, "appdata")
    if os.path.isdir(appdata_dst):
        shutil.rmtree(appdata_dst)
        print(f"  Removed leaked appdata/ from electron output")

    # 6. Self-extracting archive (one-click portable .exe)
    step("Create self-extracting archive")
    unpacked = os.path.join(HERE, "output", "win-unpacked")
    sfx_exe = os.path.join(HERE, "output", "avscrapper-1.0.1-Portable.exe")
    sfx_mod = os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"),
                           "7-Zip", "7z.sfx")
    if not os.path.isfile(sfx_mod):
        sfx_mod = os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
                               "7-Zip", "7z.sfx")
    if os.path.isfile(sfx_mod):
        # Build 7z archive
        archive_7z = os.path.join(HERE, "output", "avscraper.7z")
        subprocess.run(["7z", "a", "-mx5", archive_7z, os.path.join(unpacked, "*")],
                       check=True, cwd=os.path.join(HERE, "output"))
        # Write SFX config (no prompt = one-click)
        config = os.path.join(HERE, "output", "sfx-config.txt")
        with open(config, "w", encoding="ascii") as f:
            f.write("^;!@Install@!UTF-8!\r\n")
            f.write('Title="AV Scraper"\r\n')
            f.write('RunProgram="avscrapper.exe"\r\n')
            f.write("^;!@InstallEnd@!\r\n")
        # Combine: SFX module + config + 7z archive
        with open(sfx_exe, "wb") as out:
            with open(sfx_mod, "rb") as f:
                out.write(f.read())
            with open(config, "rb") as f:
                out.write(f.read())
            with open(archive_7z, "rb") as f:
                out.write(f.read())
        os.remove(archive_7z)
        os.remove(config)
        size_mb = os.path.getsize(sfx_exe) / (1024 * 1024)
        print(f"  {sfx_exe} ({size_mb:.0f} MB)")
    else:
        print("  7-Zip not found — skipping SFX (install 7-Zip for single-click .exe)")

    step("Build complete")
    print(f"  Unpacked app: {unpacked}")
    print(f"  Portable:     {sfx_exe}")


if __name__ == "__main__":
    main()
