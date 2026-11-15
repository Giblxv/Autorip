"""Recursos disponíveis ao processo, sem dependências opcionais."""
import math
import os
import sys
from pathlib import Path


def _read(path):
    try:
        return Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return ""


def cpu_quota():
    """Quota cgroup v2/v1 em CPUs; None quando não há limite conhecido."""
    if sys.platform != "linux":
        return None
    try:
        limit, period = _read("/sys/fs/cgroup/cpu.max").split()
        if limit == "max":
            return None
        quota, period = int(limit), int(period)
    except ValueError:
        try:
            quota = int(_read("/sys/fs/cgroup/cpu/cpu.cfs_quota_us"))
            period = int(_read("/sys/fs/cgroup/cpu/cpu.cfs_period_us"))
        except ValueError:
            return None
    return max(1, math.ceil(quota / period)) if quota > 0 and period > 0 else None


def available_memory():
    """RAM disponível em bytes, incluindo limite do container, se conhecido."""
    limits = []
    if sys.platform == "win32":
        try:
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                    (name, ctypes.c_uint64) for name in
                    ("total_phys", "avail_phys", "total_page", "avail_page",
                     "total_virtual", "avail_virtual", "avail_extended")]
            status = MemoryStatus()
            status.length = ctypes.sizeof(status)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                limits.append(status.avail_phys)
        except (AttributeError, OSError):
            pass
    elif sys.platform == "linux":
        for line in _read("/proc/meminfo").splitlines():
            if line.startswith("MemAvailable:"):
                try:
                    limits.append(int(line.split()[1]) * 1024)
                except (ValueError, IndexError):
                    pass
                break
        for maximum, current in (
            ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory.current"),
            ("/sys/fs/cgroup/memory/memory.limit_in_bytes", "/sys/fs/cgroup/memory/memory.usage_in_bytes"),
        ):
            try:
                maximum_bytes = int(_read(maximum))
                current_bytes = int(_read(current))
                # cgroup v1 usa um valor próximo de LONG_MAX para "sem limite".
                if maximum_bytes < 2**60:
                    limits.append(max(0, maximum_bytes - current_bytes))
                break
            except ValueError:
                continue
    if not limits:
        try:
            available = os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
            if available < 0:
                return None
            limits.append(available)
        except (AttributeError, OSError, ValueError):
            return None
    return min(limits)
