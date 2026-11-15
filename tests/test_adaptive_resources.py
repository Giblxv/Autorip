from types import SimpleNamespace

import pytest

from autorip import engine, resources


def test_recursos_linux_com_quota_e_ram_do_container(monkeypatch):
    files = {"/sys/fs/cgroup/cpu.max": "350000 100000",
             "/proc/meminfo": "MemAvailable: 33554432 kB",
             "/sys/fs/cgroup/memory.max": str(8 * 1024**3),
             "/sys/fs/cgroup/memory.current": str(3 * 1024**3)}
    monkeypatch.setattr(resources, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(resources, "_read", lambda path: files.get(path, ""))
    assert resources.cpu_quota() == 4
    assert resources.available_memory() == 5 * 1024**3


def test_recursos_v1_e_limite_de_ram_ja_esgotado(monkeypatch):
    files = {"/sys/fs/cgroup/cpu/cpu.cfs_quota_us": "150000",
             "/sys/fs/cgroup/cpu/cpu.cfs_period_us": "100000",
             "/sys/fs/cgroup/memory/memory.limit_in_bytes": "100",
             "/sys/fs/cgroup/memory/memory.usage_in_bytes": "101"}
    monkeypatch.setattr(resources, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(resources, "_read", lambda path: files.get(path, ""))
    assert resources.cpu_quota() == 2
    assert resources.available_memory() == 0


def test_medicao_indisponivel_usa_orcamento_conservador(monkeypatch):
    monkeypatch.setattr(resources, "sys", SimpleNamespace(platform="unknown"))
    monkeypatch.setattr(resources.os, "sysconf", lambda _: (_ for _ in ()).throw(OSError()), raising=False)
    assert resources.available_memory() is None
    assert resources.cpu_quota() is None
    assert engine._memory_budget() == 512 * 1024**2


def test_windows_usa_ram_disponivel_reportada_pela_api(monkeypatch):
    import ctypes
    def status(pointer):
        assert pointer._obj.length == 64
        pointer._obj.avail_phys = 7 * 1024**3
        return 1
    monkeypatch.setattr(resources, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(ctypes,"windll",SimpleNamespace(
        kernel32=SimpleNamespace(GlobalMemoryStatusEx=status)),raising=False)
    assert resources.available_memory() == 7 * 1024**3


def test_plano_aproveita_vinte_threads_quando_ha_trabalho_e_ram(monkeypatch):
    monkeypatch.setattr(engine, "_available_cpu_count", lambda: 20)
    monkeypatch.setattr(engine.resources, "available_memory", lambda: 32 * 1024**3)
    workers, rows = engine._render_plan(1440, 20000, 70)
    assert workers == 20 and rows == engine.STRIP
    assert workers * (rows + 140) * 1440 * engine._BYTES_PER_RENDER_PIXEL <= engine._memory_budget()


@pytest.mark.parametrize("width,rows,halo", [(1440,20000,70), (1440,20000,500)])
def test_plano_se_ajusta_ao_orcamento_compartilhado(monkeypatch, width, rows, halo):
    monkeypatch.setattr(engine, "_available_cpu_count", lambda: 20)
    monkeypatch.setattr(engine, "_memory_budget", lambda: 256 * 1024**2)
    workers, strip = engine._render_plan(width, rows, halo)
    assert 1 <= workers <= 20
    assert workers * (strip + 2*halo) * width * engine._BYTES_PER_RENDER_PIXEL <= engine._memory_budget()


def test_falha_se_uma_unica_linha_com_halo_nao_couber(monkeypatch):
    monkeypatch.setattr(engine, "_memory_budget", lambda: 1024)
    with pytest.raises(ValueError, match="RAM"):
        engine._render_plan(16441, 20000, 70)


def test_falta_de_ram_nao_altera_geometria_do_lanczos(monkeypatch):
    monkeypatch.setattr(engine, "_available_cpu_count", lambda: 20)
    monkeypatch.setattr(engine, "_host_cpu_count", lambda: 20)
    monkeypatch.setattr(engine, "_memory_budget", lambda: 512 * 1024**2)
    first=engine._render_plan(2880,6400,70)
    monkeypatch.setattr(engine,"_memory_budget",lambda:2*1024**3)
    second=engine._render_plan(2880,6400,70)
    assert first[1] == second[1] == 345
    assert second[0] > first[0]
