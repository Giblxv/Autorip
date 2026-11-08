import errno
import os
from pathlib import Path

import pytest

from autorip import paths
from autorip.paths import ProcessLock, move_unique, reserve_unique_path, safe_filename


def test_safe_filename_remove_traversal_e_caracteres_de_controle():
    assert safe_filename("../../segredo.png") == "segredo.png"
    assert safe_filename("..\\..\\NUL.png") == "_NUL.png"
    assert "\x00" not in safe_filename("arte\x00.png")
    assert len(safe_filename("a" * 300 + ".png")) <= 180
    assert len(safe_filename("a." + "x" * 10000)) <= 180


def test_reserva_e_move_geram_destinos_unicos(tmp_path):
    first = reserve_unique_path(tmp_path, "mesma.PRT")
    second = reserve_unique_path(tmp_path, "mesma.PRT")
    assert first != second
    assert first.endswith("mesma.PRT")
    assert second.endswith("mesma_001.PRT")
    (tmp_path / "origem.png").write_bytes(b"conteudo")
    moved = move_unique(tmp_path / "origem.png", tmp_path, "mesma.PRT")
    assert moved.endswith("mesma_002.PRT")
    assert Path(moved).read_bytes() == b"conteudo"


def test_process_lock_impede_duas_instancias_simultaneas(tmp_path):
    path = tmp_path / ".autorip.lock"
    first = ProcessLock(path).acquire()
    try:
        with pytest.raises(RuntimeError, match="outro processo"):
            ProcessLock(path).acquire()
    finally:
        first.release()
    with ProcessLock(path):
        pass


def test_move_entre_volumes_copia_para_temporario_antes_de_publicar(tmp_path, monkeypatch):
    source = tmp_path / "origem.bin"
    folder = tmp_path / "destino"
    folder.mkdir()
    source.write_bytes(b"x" * 10000)
    original_rename = paths._rename_unique

    def cross_device_once(src, preferred):
        if os.path.abspath(src) == os.path.abspath(source):
            raise OSError(errno.EXDEV, "cross-device")
        return original_rename(src, preferred)

    monkeypatch.setattr(paths, "_rename_unique", cross_device_once)
    target = move_unique(source, folder)
    assert not source.exists()
    assert Path(target).read_bytes() == b"x" * 10000
    assert not list(folder.glob("*.part"))


def test_move_nao_substitui_arquivo_criado_durante_publicacao(monkeypatch, tmp_path):
    source = tmp_path / "origem.png"
    folder = tmp_path / "destino"
    folder.mkdir()
    source.write_bytes(b"minha arte")
    competitor = folder / "origem.png"
    original_rename = paths._rename_noreplace
    created = {"value": False}

    def create_competitor(src, dst):
        if dst == str(competitor) and not created["value"]:
            competitor.write_bytes(b"arquivo concorrente")
            created["value"] = True
        return original_rename(src, dst)

    monkeypatch.setattr(paths, "_rename_noreplace", create_competitor)
    moved = move_unique(source, folder)
    assert competitor.read_bytes() == b"arquivo concorrente"
    assert moved == str(folder / "origem_001.png")
    assert Path(moved).read_bytes() == b"minha arte"
    assert not source.exists()



def test_fallback_sem_hardlink_publica_somente_apos_copia_completa(tmp_path, monkeypatch):
    source = tmp_path / "origem.PRT"
    data = b"PRT-TESTE" * 100_000
    source.write_bytes(data)
    destination = tmp_path / "destino.PRT"
    original_rename = paths._rename_noreplace
    seen = []

    def forbid_hardlink(*args):
        raise OSError(errno.EPERM, "hardlink indisponivel")

    def observed_rename(part, final):
        assert str(part).endswith(".part")
        assert Path(part).read_bytes() == data
        assert not destination.exists()  # nenhum arquivo final durante a copia
        seen.append((part, final))
        return original_rename(part, final)

    monkeypatch.setattr(paths.os, "link", forbid_hardlink)
    monkeypatch.setattr(paths, "_rename_noreplace", observed_rename)
    moved = paths.publish_unique_file(source, destination)
    assert moved == str(destination)
    assert destination.read_bytes() == data
    assert source.read_bytes() == data
    assert len(seen) == 1
    assert not list(tmp_path.glob(".publish.*.part"))


def test_fallback_sem_rename_atomico_falha_sem_publicar(tmp_path, monkeypatch):
    source = tmp_path / "origem.PRT"
    source.write_bytes(b"conteudo do prt")
    destination = tmp_path / "destino.PRT"

    def forbid_hardlink(*args):
        raise OSError(errno.EPERM, "hardlink indisponivel")

    def forbid_rename(*args):
        raise NotImplementedError("rename sem sobrescrita nao disponivel")

    monkeypatch.setattr(paths.os, "link", forbid_hardlink)
    monkeypatch.setattr(paths, "_rename_noreplace", forbid_rename)
    with pytest.raises(OSError, match="Publicacao atomica"):
        paths.publish_unique_file(source, destination)
    assert source.read_bytes() == b"conteudo do prt"
    assert not destination.exists()
    assert not list(tmp_path.glob(".publish.*.part"))


def test_move_unico_preserva_origem_se_filesystem_nao_tem_publicacao_atomica(tmp_path, monkeypatch):
    source = tmp_path / "entrada.png"
    source.write_bytes(b"arte original")
    destination_folder = tmp_path / "destino"
    destination_folder.mkdir()

    def forbid_hardlink(*args):
        raise OSError(errno.EPERM, "hardlink indisponivel")

    def forbid_rename(*args):
        raise NotImplementedError("rename sem sobrescrita nao disponivel")

    monkeypatch.setattr(paths.os, "link", forbid_hardlink)
    monkeypatch.setattr(paths, "_rename_noreplace", forbid_rename)
    with pytest.raises(OSError, match="Publicacao atomica"):
        move_unique(source, destination_folder)
    assert source.read_bytes() == b"arte original"
    assert not (destination_folder / "entrada.png").exists()
    assert not list(destination_folder.glob(".publish.*.part"))
