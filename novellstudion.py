"""Startpunkt för Novellstudion — används av både källkörning och exe-filen.

    python novellstudion.py
    Novellstudion.exe
"""

from __future__ import annotations

import shutil
import sys
import time
import traceback
from pathlib import Path


def _clean_stale_runtime() -> None:
    """Ta bort gamla _MEI-mappar som blivit kvar efter en krasch.

    En-filen packar upp sig bredvid exe-filen. Vid en onormal avslutning kan
    mappen bli kvar och ta upp plats. Vi rör bara mappar som är äldre än ett
    dygn, så en annan pågående instans skadas inte.
    """
    try:
        from gui import paths

        if not paths.is_frozen():
            return
        current = Path(getattr(sys, "_MEIPASS", "")).resolve()
        cutoff = time.time() - 24 * 3600
        for entry in Path(sys.executable).resolve().parent.glob("_MEI*"):
            try:
                if (
                    entry.is_dir()
                    and entry.resolve() != current
                    and entry.stat().st_mtime < cutoff
                ):
                    shutil.rmtree(entry, ignore_errors=True)
            except OSError:
                continue
    except Exception:  # noqa: BLE001 - städning får aldrig stoppa starten
        pass


def _log_path() -> Path:
    try:
        from gui import paths

        base = paths.data_root()
    except Exception:  # noqa: BLE001
        base = Path(sys.executable).resolve().parent / "Novellstudion-data"
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return base / "start.log"


def _log(message: str) -> None:
    try:
        with _log_path().open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def _error_box(message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None,
            message,
            "Novellstudion kunde inte starta",
            0x00000010 | 0x00040000 | 0x00010000,
        )
    except Exception:  # noqa: BLE001
        pass


def run() -> int:
    from gui.server import main

    return main()


if __name__ == "__main__":
    _log(
        "BOOT "
        f"frozen={getattr(sys, 'frozen', False)} exe={sys.executable!r} "
        f"cwd={Path.cwd()!r} argv={sys.argv!r} "
        f"meipass={getattr(sys, '_MEIPASS', '')!r} python={sys.version.split()[0]}"
    )
    _clean_stale_runtime()
    try:
        code = run()
    except KeyboardInterrupt:
        code = 0
    except Exception as exc:  # noqa: BLE001 - vi vill visa felet i konsolen
        traceback.print_exc()
        _log("FATAL\n" + traceback.format_exc())
        print("")
        print("Novellstudion kunde inte starta. Felet står ovan.")
        _error_box(
            f"Novellstudion kunde inte starta.\n\n{exc}\n\n"
            f"Logg: {_log_path()}"
        )
        try:
            input("Tryck Enter för att stänga fönstret...")
        except (EOFError, KeyboardInterrupt):
            pass
        code = 1
    sys.exit(code)
