"""Layering rules: shared layers never import a plugin; plugins never import each other."""
import ast
from pathlib import Path

import pytest

PKG = Path(__file__).resolve().parents[1] / "termscheck"
SHARED = ["core", "screens", "extraction", "ingest", "review", "audit", "db"]


def imports(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
    return out


@pytest.mark.parametrize("layer", SHARED)
def test_shared_layers_do_not_import_plugins(layer):
    bad = []
    for f in (PKG / layer).rglob("*.py"):
        mods = imports(f)
        if f.name == "plugin.py" and layer == "core":
            mods.discard("termscheck.plugins")   # registry bootstrap only
        bad += [(f.name, m) for m in mods if m.startswith("termscheck.plugins")]
    assert not bad, bad


def test_plugins_are_independent():
    plugins = [p for p in (PKG / "plugins").iterdir() if p.is_dir() and (p / "__init__.py").exists()]
    for p in plugins:
        others = {f"termscheck.plugins.{o.name}" for o in plugins if o != p}
        for f in p.rglob("*.py"):
            hits = [m for m in imports(f) if any(m == o or m.startswith(o + ".") for o in others)]
            assert not hits, (f, hits)


def test_registry_lists_builtin_plugins():
    from termscheck.core.plugin import all_plugins
    assert "muni" in all_plugins()
