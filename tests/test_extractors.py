"""Extraction: exclusions, parse failures, imports, and deep edges."""

from __future__ import annotations

import os
from pathlib import Path

from knowledge_surface.extractors.deep import (
    CallGraphExtractor,
    DynamicImportExtractor,
    FrameworkExtractor,
)
from knowledge_surface.extractors.python_ast import PythonASTExtractor
from knowledge_surface.representation.entities import (
    Confidence,
    EntityKind,
    RelationKind,
)
from knowledge_surface.representation.knowledge_surface import KnowledgeSurface


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def _entity(ks: KnowledgeSurface, name: str, kind: EntityKind | None = None):
    matches = [
        e for e in ks.entities()
        if e.name == name and (kind is None or e.kind == kind)
    ]
    assert matches, f"no entity named {name}"
    return matches[0]


def _module(ks: KnowledgeSurface, rel: str):
    return next(
        e for e in ks.entities(EntityKind.MODULE)
        if e.location and e.location.file == rel
    )


def _edges(ks: KnowledgeSurface, kind: RelationKind) -> set[tuple[str, str]]:
    return {(r.source, r.target) for r in ks.relationships(kind)}


def test_excluded_directories_are_not_extracted(tmp_path):
    root = _repo(tmp_path, {
        "ok.py": "x = 1\n",
        "__pycache__/x.py": "x = 1\n",
        ".venv/y.py": "x = 1\n",
        "node_modules/z.py": "x = 1\n",
        "build/b.py": "x = 1\n",
        "dist/d.py": "x = 1\n",
    })
    ks = PythonASTExtractor(root).build()
    assert ks.diagnostics["files_discovered"] == 1
    assert [e.name for e in ks.entities()] == ["ok.py"]


def test_directory_symlink_is_not_followed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.py").write_text("x = 1\n", encoding="utf-8")
    root = _repo(tmp_path, {"ok.py": "x = 1\n"})
    os.symlink(outside, root / "linked")
    ks = PythonASTExtractor(root).build()
    assert ks.diagnostics["files_discovered"] == 1
    assert all("secret" not in e.name for e in ks.entities())


def test_file_symlink_outside_root_is_skipped(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")
    root = _repo(tmp_path, {"ok.py": "x = 1\n"})
    os.symlink(outside, root / "linked.py")
    ks = PythonASTExtractor(root).build()
    assert ks.diagnostics["files_discovered"] == 1


def test_parse_failure_is_unknown_and_visible(tmp_path):
    root = _repo(tmp_path, {
        "ok.py": "x = 1\n",
        "bad.py": "def broken(:\n    pass\n",
    })
    ks = PythonASTExtractor(root).build()
    bad = _module(ks, "bad.py")
    assert bad.confidence is Confidence.UNKNOWN
    assert "parse_error" in bad.attributes
    assert ks.diagnostics["parse_failures"] == 1
    assert ks.diagnostics["parse_errors"][0]["path"] == "bad.py"
    assert ks.validate()["errors"] == []


def test_duplicate_function_names_get_distinct_ids(tmp_path):
    root = _repo(tmp_path, {"m.py": "def f():\n    pass\ndef f():\n    pass\n"})
    ks = PythonASTExtractor(root).build()
    ids = {e.id for e in ks.entities(EntityKind.FUNCTION) if e.name == "f"}
    assert len(ids) == 2


def test_relative_imports_resolve_to_local_modules(tmp_path):
    root = _repo(tmp_path, {
        "pkg/__init__.py": "from . import a\n",
        "pkg/a.py": "from . import b\n",
        "pkg/b.py": "x = 1\n",
        "pkg/sub/c.py": "from .. import b\n",
    })
    ks = PythonASTExtractor(root).build()
    b_id = _module(ks, "pkg/b.py").id
    a_id = _module(ks, "pkg/a.py").id
    c_id = _module(ks, "pkg/sub/c.py").id
    init_id = _module(ks, "pkg/__init__.py").id
    edges = _edges(ks, RelationKind.IMPORTS)
    assert (a_id, b_id) in edges
    assert (c_id, b_id) in edges
    assert (init_id, a_id) in edges


def test_unresolved_import_is_unknown_not_a_wrong_edge(tmp_path):
    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "import not_a_real_module\n",
        "other.py": "x = 1\n",
    })
    ks = PythonASTExtractor(root).build()
    external = _entity(ks, "<external:not_a_real_module>", EntityKind.MODULE)
    assert external.confidence is Confidence.UNKNOWN
    a_id = _module(ks, "pkg/a.py").id
    rel = next(
        r for r in ks.relationships(RelationKind.IMPORTS)
        if r.source == a_id and r.target == external.id
    )
    assert rel.confidence is Confidence.INFERRED
    assert "not_a_real_module" in rel.evidence


def test_build_is_deterministic(tmp_path):
    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": "from . import b\n",
        "pkg/b.py": "x = 1\n",
    })
    assert PythonASTExtractor(root).build().to_dict() == (
        PythonASTExtractor(root).build().to_dict()
    )


def test_max_files_truncation_is_reported(tmp_path):
    root = _repo(tmp_path, {f"{i}.py": "x = 1\n" for i in range(3)})
    ks = PythonASTExtractor(root, max_files=2).build()
    assert ks.diagnostics["files_discovered"] == 3
    assert ks.diagnostics["files_parsed"] == 2
    assert ks.diagnostics["truncated"] is True


def test_call_graph_adds_edges_between_top_level_functions(tmp_path):
    root = _repo(tmp_path, {
        "m.py": "def caller():\n    callee()\n\ndef callee():\n    pass\n",
    })
    ks = PythonASTExtractor(root).build()
    CallGraphExtractor().enrich(ks, root)
    caller = _entity(ks, "caller", EntityKind.FUNCTION)
    callee = _entity(ks, "callee", EntityKind.FUNCTION)
    assert (caller.id, callee.id) in _edges(ks, RelationKind.CALLS)
    assert ks.diagnostics["call_graph"]["edges_added"] == 1


def test_shadowed_nested_function_is_not_a_false_edge(tmp_path):
    root = _repo(tmp_path, {
        "m.py": (
            "def caller():\n"
            "    def callee():\n"
            "        pass\n"
            "    callee()\n"
            "\n"
            "def callee():\n"
            "    pass\n"
        ),
    })
    ks = PythonASTExtractor(root).build()
    CallGraphExtractor().enrich(ks, root)
    caller = _entity(ks, "caller", EntityKind.FUNCTION)
    assert not any(src == caller.id for src, _ in _edges(ks, RelationKind.CALLS))


def test_ambiguous_call_targets_are_skipped_and_counted(tmp_path):
    root = _repo(tmp_path, {
        "a.py": "def helper():\n    pass\n",
        "b.py": "def helper():\n    pass\n",
        "c.py": "def caller():\n    helper()\n",
    })
    ks = PythonASTExtractor(root).build()
    CallGraphExtractor().enrich(ks, root)
    caller = _entity(ks, "caller", EntityKind.FUNCTION)
    assert not any(src == caller.id for src, _ in _edges(ks, RelationKind.CALLS))
    assert ks.diagnostics["call_graph"]["ambiguous_calls_skipped"] == 1


def test_dynamic_import_of_local_module_resolves(tmp_path):
    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/b.py": "x = 1\n",
        "pkg/a.py": (
            "import importlib\n"
            "def load():\n"
            "    return importlib.import_module('pkg.b')\n"
        ),
    })
    ks = PythonASTExtractor(root).build()
    DynamicImportExtractor().enrich(ks, root)
    a_id = _module(ks, "pkg/a.py").id
    b_id = _module(ks, "pkg/b.py").id
    assert (a_id, b_id) in _edges(ks, RelationKind.IMPORTS)


def test_dynamic_import_fstring_is_unknown(tmp_path):
    root = _repo(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": (
            "import importlib\n"
            "def load(name):\n"
            "    return importlib.import_module(f'pkg.{name}')\n"
        ),
    })
    ks = PythonASTExtractor(root).build()
    DynamicImportExtractor().enrich(ks, root)
    unknown = [e for e in ks.entities() if e.name == "<dynamic:pkg.*>"]
    assert unknown and unknown[0].confidence is Confidence.UNKNOWN
    assert ks.diagnostics["dynamic_imports"]["unresolved_targets"] == 1


def test_framework_decorator_creates_inferred_capability(tmp_path):
    root = _repo(tmp_path, {
        "app.py": "@app.route('/')\ndef index():\n    return 'ok'\n",
    })
    ks = PythonASTExtractor(root).build()
    FrameworkExtractor().enrich(ks, root)
    capability = _entity(ks, "framework:route", EntityKind.CAPABILITY)
    assert capability.confidence is Confidence.INFERRED
    index = _entity(ks, "index", EntityKind.FUNCTION)
    assert (index.id, capability.id) in _edges(ks, RelationKind.REQUIRES)
