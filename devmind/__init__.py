# DevMind: Codebase Memory for Developers
import sys as _sys

if _sys.version_info < (3, 10):
    _sys.stderr.write(
        f"DevMind requires Python 3.10 or newer (you have "
        f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}).\n"
        "Several modules use Python 3.10+ syntax (e.g. `str | list[str]` union "
        "types) and will fail to import on older interpreters.\n"
        "Please upgrade: https://www.python.org/downloads/\n"
    )
    _sys.exit(1)

__version__ = "0.3.7"
