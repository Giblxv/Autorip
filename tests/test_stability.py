"""Estabilidade em lote sem sleeps reais ou dependência do scheduler."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def stability():
    # Namespace isolado: fixtures de App deixam observadores daemon em execução.
    # O relógio simulado não pode afetar esses observadores nem o time global.
    path = Path(__file__).resolve().parents[1] / "autorip" / "watcher.py"
    spec = importlib.util.spec_from_file_location("autorip._stability_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lote_preserva_janela_e_rejeita_alterados_removidos_e_vazios(stability, tmp_path):
    paths = [tmp_path / name for name in ("ok", "changed", "removed", "empty", "directory", "missing")]
    for path in paths[:3]:
        path.write_bytes(b"abc")
    paths[3].touch()
    paths[4].mkdir()
    calls = []

    def wait(seconds):
        calls.append(seconds)
        paths[1].write_bytes(b"abcdef")
        paths[2].unlink()

    stability.time = SimpleNamespace(sleep=wait)
    stable = list(stability._stable_files(paths, wait=.5))
    assert [path for path, _ in stable] == paths[:1]
    assert calls == [.5]


def test_revalida_arquivo_modificado_enquanto_o_anterior_era_consumido(stability, tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.write_bytes(b"one")
    second.write_bytes(b"two")
    stability.time = SimpleNamespace(sleep=lambda _: None)
    iterator = stability._stable_files([first, second], wait=.5)
    assert next(iterator)[0] == first
    second.write_bytes(b"still copying")
    assert list(iterator) == []


def test_substituicao_com_mesmo_tamanho_e_mtime_nao_e_estavel(stability, tmp_path):
    path = tmp_path / "replaced"
    path.write_bytes(b"old")
    original = path.stat()

    def replace(_seconds):
        path.rename(tmp_path / "original")
        path.write_bytes(b"new")
        os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))

    stability.time = SimpleNamespace(sleep=replace)
    assert list(stability._stable_files([path])) == []


def test_lote_sem_arquivos_validos_nao_espera(stability, tmp_path):
    empty = tmp_path / "empty"
    empty.touch()
    stability.time = SimpleNamespace(sleep=lambda _: pytest.fail("Espera sem arquivos válidos"))
    assert list(stability._stable_files([tmp_path, empty, tmp_path / "missing"])) == []


def test_assinatura_usa_uma_consulta_sem_seguir_links(stability, tmp_path):
    path = tmp_path / "file"
    path.write_bytes(b"data")
    calls = []

    def stat_once(path, *, follow_symlinks):
        calls.append(follow_symlinks)
        return os.stat(path, follow_symlinks=follow_symlinks)

    stability.os = SimpleNamespace(stat=stat_once)
    assert stability._signature(path)[2] == 4
    assert stability._signature(tmp_path) is None
    assert calls == [False, False]
