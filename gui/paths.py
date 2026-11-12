"""Sökvägar som fungerar både i utvecklingsmappen och i en fristående exe.

I källkoden ligger index och metadata i projektmappen. När programmet paketeras
med PyInstaller hamnar de i den tillfälliga utpackningsmappen (``_MEIPASS``),
medan sådant som skrivs — noveller, inställningar, historik — hamnar i
``Novellstudion-data`` bredvid exe-filen.
"""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_root() -> Path:
    """Mappen där exe-filen (eller projektet) ligger."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    """Mappen där de medföljande filerna ligger."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_root()))
    return app_root()


def data_root() -> Path:
    """Mappen där användarens egna filer sparas."""
    if is_frozen():
        return app_root() / "Novellstudion-data"
    return app_root() / "out"


def resource(*parts: str) -> Path:
    return resource_root().joinpath(*parts)


def relative_base() -> Path:
    """Bas för relativa sökvägar som användaren skriver in."""
    return data_root() if is_frozen() else app_root()


def default_novel_folder() -> str:
    if is_frozen():
        return str(data_root() / "noveller")
    return "out/noveller"
