"""Command-line interface for the Knowledge Surface."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .action.verified_action import ChangeEvaluator
from .drift.detector import SemanticDriftDetector
from .extractors.python_ast import PythonASTExtractor
from .representation.invariants import HeuristicInvariantExtractor
from .representation.knowledge_surface import KnowledgeSurface
from .verification.change import ChangeSet
from .verification.config import load_rules
from .verification.engine import SemanticVerifier
from .verification.feedback import to_markdown as verification_markdown

console = Console()


@click.group()
def cli() -> None:
    """Knowledge Surface: structured representation of software's two architectures."""


@cli.command("build")
@click.argument("path", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default="knowledge-surface.json")
@click.option("--name", default="knowledge-surface")
def build(path: str, output: str, name: str) -> None:
    """Build a Knowledge Surface from a source tree."""
    ks = PythonASTExtractor(path).build(name=name)
    HeuristicInvariantExtractor(path).extract(ks)
    Path(output).write_text(json.dumps(ks.to_dict(), indent=2, default=str))
    console.print(f"[green]Built[/green] {ks!r} -> {output}")


@cli.command("inspect")
@click.argument("ks_file", type=click.Path(exists=True))
def inspect(ks_file: str) -> None:
    """Inspect a Knowledge Surface."""
    data = json.loads(Path(ks_file).read_text())
    ks = KnowledgeSurface.from_dict(data)
    t = Table(title=ks.name)
    t.add_column("Metric")
    t.add_column("Value")
    for k, v in ks.stats().items():
        t.add_row(k, str(v))
    console.print(t)
    console.print("Confidence:", ks.confidence_summary())
    unknowns = ks.unknowns()
    if unknowns:
        console.print(f"[yellow]{len(unknowns)} unknown(s)[/yellow]")
        for u in unknowns[:10]:
            console.print("  -", u)


@cli.command("query")
@click.argument("ks_file", type=click.Path(exists=True))
@click.argument("name")
def query(ks_file: str, name: str) -> None:
    """Find entities by name substring."""
    data = json.loads(Path(ks_file).read_text())
    ks = KnowledgeSurface.from_dict(data)
    matches = [e for e in ks.entities() if name.lower() in e.name.lower()]
    if not matches:
        console.print("[red]no matches[/red]")
        return
    for e in matches:
        console.print(f"{e.id}  {e.kind.value:10}  {e.name}  ({e.confidence.value})")
        invs = ks.invariants_for(e.id)
        if invs:
            console.print(f"   invariants: {[i.name for i in invs]}")


@cli.command("check")
@click.argument("ks_file", type=click.Path(exists=True))
@click.argument("entity_id")
@click.option("--action", type=click.Choice(["remove", "add"]), default="remove")
def check(ks_file: str, entity_id: str, action: str) -> None:
    """Evaluate a proposed change against the Knowledge Surface."""
    data = json.loads(Path(ks_file).read_text())
    ks = KnowledgeSurface.from_dict(data)
    ev = ChangeEvaluator(ks)
    if action == "remove":
        va = ev.evaluate_remove_entity(entity_id)
    else:
        console.print("[red]add requires a spec file; use the Python API[/red]")
        return
    console.print(f"approved: {va.approved}")
    console.print(va.verdict.summary())
    for v in va.verdict.violations:
        console.print(f"  [{v.severity}] {v.message}")
    if va.propagation:
        console.print(f"blast radius: {va.propagation.blast_radius}")


@cli.command("drift")
@click.argument("before", type=click.Path(exists=True))
@click.argument("after", type=click.Path(exists=True))
def drift_cmd(before: str, after: str) -> None:
    """Compare two Knowledge Surfaces for semantic drift."""
    b = KnowledgeSurface.from_dict(json.loads(Path(before).read_text()))
    a = KnowledgeSurface.from_dict(json.loads(Path(after).read_text()))
    rep = SemanticDriftDetector(b, a).detect()
    console.print(rep.summary())
    for f in rep.findings:
        console.print(f"  [{f.severity}] {f.kind}: {f.message}")


@cli.command("report")
@click.argument("ks_file", type=click.Path(exists=True))
def report(ks_file: str) -> None:
    """Print a full architectural report."""
    data = json.loads(Path(ks_file).read_text())
    ks = KnowledgeSurface.from_dict(data)
    console.print(f"# {ks.name}")
    console.print(f"entities={len(ks.entities())} relationships={len(ks.relationships())} invariants={len(ks.invariants())}")
    console.print("\n## Invariants (Second Architecture)")
    for inv in ks.invariants():
        console.print(f"- [{inv.confidence.value}] {inv.name}: {inv.description}  scope={inv.scope}")
    console.print("\n## Unknowns (honest uncertainty)")
    for u in ks.unknowns():
        console.print("  -", u)


@cli.command("verify")
@click.argument("path", type=click.Path(exists=True))
@click.option("--patch", type=click.Path(exists=True), required=True, help="Unified diff to verify.")
@click.option("--rules", type=click.Path(exists=True), required=True, help="JSON rule config.")
@click.option("--json-out", type=click.Path(), default=None)
def verify(path: str, patch: str, rules: str, json_out: str | None) -> None:
    """Verify a proposed patch against architectural invariants."""
    rule_list, allow = load_rules(rules)
    changes = ChangeSet.from_patch(Path(patch).read_text())
    report = SemanticVerifier(rule_list, allow).verify(Path(path), changes)
    console.print(verification_markdown(report))
    if json_out:
        Path(json_out).write_text(json.dumps(report.to_dict(), indent=2))
    if not report.approved:
        raise SystemExit(1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
