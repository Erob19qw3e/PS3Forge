"""Start system programs without inheriting a frozen app's DLL search path."""
import os
import subprocess
import sys
import threading
from pathlib import Path

_launch_lock = threading.Lock()


def external_environment(env, bundle=None):
    result = dict(env)
    if not bundle:
        return result
    root = os.path.normcase(os.path.abspath(str(bundle)))

    def bundled(value):
        path = os.path.normcase(os.path.abspath(os.path.expandvars(value.strip('"'))))
        return path == root or path.startswith(root + os.sep)

    result['PATH'] = os.pathsep.join(p for p in result.get('PATH', '').split(os.pathsep)
                                   if p and not bundled(p))
    for key in list(result):
        if key.startswith('_PYI_') or key in ('_MEIPASS2', 'PYTHONHOME', 'PYTHONPATH', 'PS3FORGE_HOME'):
            result.pop(key, None)
        elif key in ('QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH', 'QML2_IMPORT_PATH',
                     'QML_IMPORT_PATH', 'QTWEBENGINEPROCESS_PATH', 'QTWEBENGINE_RESOURCES_PATH',
                     'QTWEBENGINE_LOCALES_PATH'):
            # An external Qt program must discover its own matching plugins.
            result.pop(key, None)
    return result


def launch_external(args, *, cwd, env=None, popen=None):
    """Restore the parent's exact DLL search directory even if CreateProcess fails."""
    popen = popen or subprocess.Popen
    child_env = external_environment(os.environ if env is None else env,
                                     getattr(sys, '_MEIPASS', None))
    with _launch_lock:
        kernel = None
        previous = None
        if sys.platform == 'win32' and getattr(sys, 'frozen', False):
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.GetDllDirectoryW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
            kernel.GetDllDirectoryW.restype = wintypes.DWORD
            kernel.SetDllDirectoryW.argtypes = [wintypes.LPCWSTR]
            kernel.SetDllDirectoryW.restype = wintypes.BOOL
            needed = kernel.GetDllDirectoryW(0, None)
            if needed:
                buffer = ctypes.create_unicode_buffer(needed + 1)
                if not kernel.GetDllDirectoryW(len(buffer), buffer):
                    raise ctypes.WinError(ctypes.get_last_error())
                previous = buffer.value
            if not kernel.SetDllDirectoryW(None):
                raise ctypes.WinError(ctypes.get_last_error())
        try:
            return popen(args, cwd=str(cwd), env=child_env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        finally:
            if kernel is not None and not kernel.SetDllDirectoryW(previous):
                import ctypes
                raise ctypes.WinError(ctypes.get_last_error())
