import json
from pathlib import Path


def test_manifest_uses_the_current_homeassistant_config_map_name():
    manifest = json.loads(
        (Path(__file__).parents[1] / "config.json").read_text(encoding="utf-8")
    )

    assert "homeassistant_config" in manifest["map"]
    assert "config" not in manifest["map"]
