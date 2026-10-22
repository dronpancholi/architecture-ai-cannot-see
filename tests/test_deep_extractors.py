"""Tests for deeper code understanding: call graph, dynamic imports, frameworks."""

from pathlib import Path

from knowledge_surface import build_surface
from knowledge_surface.representation.entities import EntityKind, RelationKind

FIX = Path(__file__).resolve().parents[1] / "benchmarks" / "fixtures"


def test_call_graph_edges():
    ks = build_surface(FIX / "layered_webapp")
    calls = ks.relationships(RelationKind.CALLS)
    assert calls, "expected name-resolved call edges"
    assert any(r.confidence.value == "inferred" for r in calls)


def test_dynamic_import_detected():
    ks = build_surface(FIX / "plugin_host")
    names = {e.name for e in ks.entities(EntityKind.MODULE)}
    assert any("dynamic" in n for n in names), names
    assert any("dynamic" in n for n in names)


def test_cross_file_call_propagation():
    ks = build_surface(FIX / "layered_webapp")
    repo_insert = next(
        e for e in ks.entities(EntityKind.FUNCTION) if e.name.endswith("OrderRepository.insert")
    )
    dependents = ks.dependents(repo_insert.id)
    names = {ks.entity(d).name for d in dependents if ks.entity(d)}
    assert any("place" in n for n in names), names


def test_framework_decorators_surface_capabilities():
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        (root / "api.py").write_text(
            "def route(fn):\n    return fn\n\n@route\ndef home() -> str:\n    return 'ok'\n"
        )
        ks = build_surface(root)
        caps = ks.entities(EntityKind.CAPABILITY)
        assert any(c.name == "framework:route" for c in caps)
