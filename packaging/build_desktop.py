import platform
import subprocess
import sys
import zipfile
import argparse
import importlib.util
import time
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    print(">", " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def zip_output(dist_dir: Path, archive_name: str) -> Path:
    exe_candidates = [dist_dir / "NeuroGame", dist_dir / "NeuroGame.exe"]
    target = next((p for p in exe_candidates if p.exists()), None)
    if target is None:
        raise FileNotFoundError("Build output not found in dist/.")

    archive_path = dist_dir / archive_name
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(target, arcname=target.name)
    return archive_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build desktop package with PyInstaller")
    parser.add_argument(
        "--install-deps",
        action="store_true",
        help="Install/upgrade PyInstaller before build",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    spec = root / "packaging" / "neurogame.spec"
    dist = root / "dist"

    print("[1/4] Checking PyInstaller...")
    pyinstaller_installed = importlib.util.find_spec("PyInstaller") is not None
    if not pyinstaller_installed and args.install_deps:
        install_cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--upgrade",
            "--timeout",
            "180",
            "--retries",
            "5",
            "pyinstaller",
        ]
        last_err: Exception | None = None
        for attempt in range(1, 4):
            try:
                print(f"Installing PyInstaller (attempt {attempt}/3)...")
                run(install_cmd, cwd=root)
                last_err = None
                break
            except subprocess.CalledProcessError as exc:
                last_err = exc
                if attempt < 3:
                    time.sleep(2 * attempt)
        if last_err is not None:
            raise last_err
        pyinstaller_installed = importlib.util.find_spec("PyInstaller") is not None
    if not pyinstaller_installed:
        print(
            "PyInstaller is not installed. Install it first:\n"
            f"  {sys.executable} -m pip install pyinstaller\n"
            "or run this script with --install-deps"
        )
        sys.exit(2)

    print("[2/4] Building desktop executable...")
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)], cwd=root)

    print("[3/4] Preparing release archive...")
    platform_tag = f"{platform.system().lower()}-{platform.machine().lower()}"
    archive = zip_output(dist, f"neurogame-{platform_tag}.zip")

    print("[4/4] Done.")
    print(f"Executable: {dist / 'NeuroGame'} (or NeuroGame.exe)")
    print(f"Archive: {archive}")


if __name__ == "__main__":
    main()
