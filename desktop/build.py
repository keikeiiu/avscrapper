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
        run(["npm", "install"])

    # 5. Electron-builder (unpacked — avoids Windows code-signing symlink issues)
    step("Electron-builder: package app")
    run(["npx", "electron-builder", "--dir", "--win"])

    # 6. Archive for distribution
    step("Create distribution archive")
    import tarfile
    unpacked = os.path.join(HERE, "output", "win-unpacked")
    archive = os.path.join(HERE, "output", "AVScraper-1.0.0-portable.tar.gz")
    with tarfile.open(archive, "w:gz") as tar:
        for item in os.listdir(unpacked):
            tar.add(os.path.join(unpacked, item), arcname=item)
    size_mb = os.path.getsize(archive) / (1024 * 1024)
    print(f"  {archive} ({size_mb:.0f} MB)")

    step("Build complete")
    print(f"  Unpacked app: {unpacked}")
    print(f"  Archive:      {archive}")


if __name__ == "__main__":
    main()
