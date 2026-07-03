"""The plugin/marketplace validator used by CI."""

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
VALIDATE_PY = REPO_ROOT / "scripts" / "validate_plugins.py"

spec = importlib.util.spec_from_file_location("validate_plugins", VALIDATE_PY)
validate_plugins = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_plugins)


def test_repo_plugins_are_valid():
    """The shipped plugins must always validate — this is the CI gate."""
    assert validate_plugins.validate() == []


def test_cli_exit_code_and_summary():
    proc = subprocess.run(
        [sys.executable, str(VALIDATE_PY)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr
    assert "plugins OK" in proc.stdout


def test_detects_broken_manifest(tmp_path, monkeypatch):
    plugin = tmp_path / "plugins" / "broken" / ".claude-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"version": "1.0.0"}')  # no name
    marketplace = tmp_path / ".claude-plugin"
    marketplace.mkdir()
    (marketplace / "marketplace.json").write_text('{"plugins": []}')

    monkeypatch.setattr(validate_plugins, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_plugins, "PLUGINS_DIR", tmp_path / "plugins")
    monkeypatch.setattr(validate_plugins, "MARKETPLACE", marketplace / "marketplace.json")

    problems = validate_plugins.validate()
    assert any("missing required field 'name'" in p for p in problems)


def test_detects_unregistered_plugin(tmp_path, monkeypatch):
    plugin = tmp_path / "plugins" / "orphan" / ".claude-plugin"
    plugin.mkdir(parents=True)
    (plugin / "plugin.json").write_text('{"name": "orphan", "version": "1.0.0"}')
    marketplace = tmp_path / ".claude-plugin"
    marketplace.mkdir()
    (marketplace / "marketplace.json").write_text('{"plugins": []}')

    monkeypatch.setattr(validate_plugins, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_plugins, "PLUGINS_DIR", tmp_path / "plugins")
    monkeypatch.setattr(validate_plugins, "MARKETPLACE", marketplace / "marketplace.json")

    problems = validate_plugins.validate()
    assert any("not registered in marketplace.json" in p for p in problems)


def test_detects_dangling_marketplace_source(tmp_path, monkeypatch):
    (tmp_path / "plugins").mkdir()
    marketplace = tmp_path / ".claude-plugin"
    marketplace.mkdir()
    (marketplace / "marketplace.json").write_text(
        '{"plugins": [{"name": "ghost", "source": {"type": "path", "path": "./plugins/ghost"}}]}'
    )

    monkeypatch.setattr(validate_plugins, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(validate_plugins, "PLUGINS_DIR", tmp_path / "plugins")
    monkeypatch.setattr(validate_plugins, "MARKETPLACE", marketplace / "marketplace.json")

    problems = validate_plugins.validate()
    assert any("does not exist" in p for p in problems)
