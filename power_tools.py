from __future__ import annotations

import os
import subprocess


def sleep_pc() -> bool:
    if os.name != "nt":
        return False
    try:
        subprocess.run(
            ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=False, creationflags=0x08000000, timeout=10
        )
        return True
    except Exception:
        return False


def kill_game() -> bool:
    if os.name != "nt":
        return False
    ok = False
    for image in ("FortniteClient-Win64-Shipping.exe", "FortniteLauncher.exe"):
        try:
            r = subprocess.run(
                ["taskkill", "/IM", image, "/F"], check=False, creationflags=0x08000000, capture_output=True, timeout=10
            )
            ok = r.returncode == 0 or ok
        except Exception:
            pass
    return ok


def relaunch_game(settings):
    import relauncher

    return relauncher.manual_relaunch(settings)
