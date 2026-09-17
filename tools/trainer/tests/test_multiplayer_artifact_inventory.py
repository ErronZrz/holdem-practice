from pathlib import Path

import pytest

from multiplayer_cfr.artifact_inventory import (
    ArtifactInventoryError,
    InventorySlot,
    inventory_declared_artifacts,
    remove_declared_artifacts,
    require_empty_artifact_root,
)


def test_inventory_requires_empty_root_and_seals_only_declared_regular_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    require_empty_artifact_root(root)
    slots = (
        InventorySlot("measurement.json", 100),
        InventorySlot("strategy.json", 100),
    )
    (root / "measurement.json").write_bytes(b"measurement")
    (root / "strategy.json").write_bytes(b"strategy")

    inventory = inventory_declared_artifacts(
        root,
        slots,
        required_names=frozenset({"measurement.json", "strategy.json"}),
    )

    assert [entry.relative_name for entry in inventory] == ["measurement.json", "strategy.json"]
    assert all(len(entry.sha256) == 64 for entry in inventory)


def test_inventory_rejects_unknown_files_and_cleanup_is_fail_closed(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    root.mkdir()
    slots = (InventorySlot("measurement.json", 100),)
    (root / "measurement.json").write_bytes(b"measurement")
    (root / "unknown.bin").write_bytes(b"unknown")

    with pytest.raises(ArtifactInventoryError):
        inventory_declared_artifacts(root, slots, required_names=frozenset({"measurement.json"}))
    with pytest.raises(ArtifactInventoryError):
        remove_declared_artifacts(root, slots)
