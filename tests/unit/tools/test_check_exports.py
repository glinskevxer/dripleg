from __future__ import annotations

import importlib

import pytest

from dripleg.tools.check_exports import check, main, modules


def test_this_build_declares_its_exports_cleanly() -> None:
    assert check() == []


def test_the_walk_finds_every_layer() -> None:
    found = modules()
    for name in (
        "dripleg.units.pressure",
        "dripleg.steam.table",
        "dripleg.diagnosis.engine",
        "dripleg.loss.napier",
        "dripleg.store.db",
        "dripleg.cli.main",
        "dripleg.tools.smoke",
    ):
        assert name in found
    assert found == sorted(found)


def test_every_declared_export_imports() -> None:
    for name in modules():
        module = importlib.import_module(name)
        for exported in getattr(module, "__all__", []):
            assert hasattr(module, exported), f"{name}.{exported}"


def test_every_all_is_sorted() -> None:
    for name in modules():
        module = importlib.import_module(name)
        declared = getattr(module, "__all__", None)
        if declared is None:
            continue
        assert list(declared) == sorted(declared), name


def test_no_all_repeats_a_name() -> None:
    for name in modules():
        module = importlib.import_module(name)
        declared = getattr(module, "__all__", [])
        assert len(set(declared)) == len(declared), name


def test_the_gate_passes_and_counts(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "every declared export present and in order" in capsys.readouterr().out


def test_the_gate_can_list_the_modules(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--list"]) == 0
    printed = capsys.readouterr().out
    assert "dripleg.units.money" in printed


def test_the_package_root_exports_its_version() -> None:
    import dripleg

    assert "__version__" in dripleg.__all__
    assert dripleg.__version__
