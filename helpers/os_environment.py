import sys
import os

# Check if we're running inside a pyinstaller bundled (it's an exe)


def isBundelled():
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def isWindows():
    return sys.platform.startswith("win32")


def isLinux():
    return sys.platform.startswith("linux")


def isMacOS():
    return sys.platform.startswith("darwin")


# This must be used to that relative file paths resolve inside the bundled versions.


def resolve_local_file_path(relative_path: str):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path: str = sys._MEIPASS
    except Exception :
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


# Use this to resolve paths to resources not bundled within the bundled exe.


def resolve_external_file_path(relative_path: str):
    if not relative_path.startswith("/"):
        relative_path = "/" + relative_path
    # Pass through abspath to correct any /'s with \'s on Windows
    return os.path.abspath(os.getcwd() + relative_path)
