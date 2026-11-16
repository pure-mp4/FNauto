from __future__ import annotations

import argparse
import os
import subprocess
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--icon", required=True)
    parser.add_argument("--version-file", required=True)
    args = parser.parse_args()
    icon = os.path.abspath(args.icon)
    if not os.path.isfile(icon):
        print(f"Missing icon: {icon}", flush=True)
        return 1
    version_file = os.path.abspath(args.version_file)
    if not os.path.isfile(version_file):
        print(f"Missing version file: {version_file}", flush=True)
        return 1
    env = dict(os.environ, FNAUTO_ICON=icon, FNAUTO_VERSION_FILE=version_file)
    return subprocess.call(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", "dist", "FNauto_Qt.spec"], env=env
    )


if __name__ == "__main__":
    raise SystemExit(main())
