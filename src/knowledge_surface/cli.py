"""Command-line interface for the Knowledge Surface.

Exit-code contract:

* ``0`` success / approved
* ``1`` policy rejection (verification blocked, drift found with --fail-on-drift)
* ``2`` input error (missing file, malformed JSON, invalid patch, bad rule config)
* ``3`` verification indeterminate (unknown result under a blocking policy)
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from .action.verified_action import ChangeEvaluator
from .drift.detector import SemanticDriftDetector
from .pipeline import build_surface
from .representation.entities import Entity
from .representation.knowledge_surface import KnowledgeSurface, SchemaError
from .verification.change import ChangeError, ChangeSet, PatchError
from .verification.config import load_rules
from .verification.engine import SemanticVerifier
from .verification.feedback import to_markdown as verification_markdown

console = Console()


def _fail(message: str, code: int = 2) -> None:
    console.print(f"[red]error:[/red] {message}")
    raise SystemExit(code)


def _load_surface(path: str) -> KnowledgeSurface:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _fail(f"cannot read {path}: {exc}")
    try:
        return KnowledgeSurface.from_dict(data)
    except SchemaError as exc:
        _fail(f"invalid Knowledge Surface {path}: {exc}")


@click.group()
def cli() -> None:
    """Knowledge Surface: structured representation of software's two architectures."""


@cli.command("build")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", type=click.Path(), default="knowledge-surface.json")
@click.option("--name", default="knowledge-surface")
@click.option("--no-deep", is_flag=True, help="Skip call-graph/dynamic-import/framework enrichment.")
def build(path: str, output: str, name: str, no_deep: bool) -> None:
    """Build a Knowledge Surface from a source tree."""
    try:
        ks = build_surface(path, name=name, deep=not no_deep)
    except OSError as exc:
        _fail(f"cannot build surface: {exc}")
    try:
        Path(output).write_text(
            json.dumps(ks.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        _fail(f"cannot write {output}: {exc}")
    console.print(f"[green]Built[/green] {ks!r} -> {output}")


@cli.command("inspect")
@click.argument("ks_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def inspect(ks_file: str, as_json: bool) -> None:
    """Inspect a Knowledge Surface."""
    ks = _load_surface(ks_file)
    if as_json:
        click.echo(json.dumps(ks.to_dict(), indent=2, sort_keys=True))
        return
    table = Table(title=ks.name)
    table.add_column("Metric")
    table.add_column("Value")
    for k, v in ks.stats().items():
        table.add_row(k, str(v))
    console.print(table)
    console.print("Confidence:", ks.confidence_summary())
    diagnostics = ks.diagnostics
    if diagnostics.get("parse_failures"):
        console.print(f"[yellow]{diagnostics['parse_failures']} parse failure(s)[/yellow]")
        for error in diagnostics.get("parse_errors", [])[:10]:
            console.print(f"  - {error['path']}: {error['error']}")
    unknowns = ks.unknowns()
    if unknowns:
        console.print(f"[yellow]{len(unknowns)} unknown(s)[/yellow]")
        for unknown in unknowns[:10]:
            console.print("  -", unknown)
    validation = ks.validate()
    for warning in validation["warnings"]:
        console.print(f"[yellow]warning:[/yellow] {warning}")


@cli.command("query")
@click.argument("ks_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("name")
@click.option("--json", "as_json", is_flag=True)
def query(ks_file: str, name: str, as_json: bool) -> None:
    """Find entities by name substring."""
    ks = _load_surface(ks_file)
    matches = [e for e in ks.entities() if name.lower() in e.name.lower()]
    if as_json:
        click.echo(json.dumps([
            {"id": e.id, "kind": e.kind.value, "name": e.name,
             "confidence": e.confidence.value,
             "invariants": [i.name for i in ks.invariants_for(e.id)]}
            for e in matches
        ], indent=2, sort_keys=True))
        return
    if not matches:
        console.print("[yellow]no matches[/yellow]")
        raise SystemExit(1)
    for entity in matches:
        console.print(
            f"{entity.id}  {entity.kind.value:10}  {entity.name}  ({entity.confidence.value})"
        )
        invariants = ks.invariants_for(entity.id)
        if invariants:
            console.print(f"   invariants: {[i.name for i in invariants]}")


@cli.command("check")
@click.argument("ks_file", type=click.Path(exists=True, dir_okay=False))
@click.argument("entity_id", required=False)
@click.option("--action", type=click.Choice(["remove", "add"]), default="remove")
@click.option("--spec", type=click.Path(exists=True, dir_okay=False),
              help="JSON entity document for --action add.")
def check(ks_file: str, entity_id: str, action: str, spec: str | None) -> None:
    """Evaluate a proposed change against the Knowledge Surface."""
    ks = _load_surface(ks_file)
    evaluator = ChangeEvaluator(ks)
    if action == "add":
        if not spec:
            _fail("--action add requires --spec with a JSON entity", 2)
        if entity_id:
            console.print("[yellow]note: entity_id is ignored for --action add[/yellow]")
        try:
            entity = Entity.model_validate(json.loads(Path(spec).read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            _fail(f"invalid entity spec: {exc}")
        va = evaluator.evaluate_add_entity(entity)
    else:
        if not entity_id:
            _fail("--action remove requires an entity_id", 2)
        if ks.entity(entity_id) is None:
            _fail(f"unknown entity: {entity_id}", 2)
        va = evaluator.evaluate_remove_entity(entity_id)
    console.print(f"approved: {va.approved}")
    console.print(va.verdict.summary())
    for violation in va.verdict.violations:
        console.print(f"  [{violation.severity}] {violation.message}")
    if va.propagation:
        console.print(f"blast radius: {va.propagation.blast_radius}")
    raise SystemExit(0 if va.approved else 1)


@cli.command("drift")
@click.argument("before", type=click.Path(exists=True, dir_okay=False))
@click.argument("after", type=click.Path(exists=True, dir_okay=False))
@click.option("--json", "as_json", is_flag=True)
@click.option("--fail-on-drift", is_flag=True)
def drift_cmd(before: str, after: str, as_json: bool, fail_on_drift: bool) -> None:
    """Compare two Knowledge Surfaces for semantic drift."""
    b = _load_surface(before)
    a = _load_surface(after)
    report = SemanticDriftDetector(b, a).detect()
    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    else:
        console.print(report.summary())
        for finding in report.findings:
            console.print(f"  [{finding.severity}] {finding.kind}: {finding.message}")
    if fail_on_drift and report.has_drift:
        raise SystemExit(1)


@cli.command("report")
@click.argument("ks_file", type=click.Path(exists=True, dir_okay=False))
def report(ks_file: str) -> None:
    """Print a full architectural report."""
    ks = _load_surface(ks_file)
    console.print(f"# {ks.name}")
    console.print(
        f"entities={len(ks.entities())} relationships={len(ks.relationships())} "
        f"invariants={len(ks.invariants())}"
    )
    diagnostics = ks.diagnostics
    if diagnostics:
        console.print(
            f"files={diagnostics.get('files_discovered', '?')} "
            f"parsed={diagnostics.get('files_parsed', '?')} "
            f"parse_failures={diagnostics.get('parse_failures', '?')} "
            f"unresolved_imports={diagnostics.get('unresolved_imports', '?')}"
        )
    console.print("\n## Invariants (Second Architecture)")
    for inv in ks.invariants():
        console.print(
            f"- [{inv.confidence.value}] {inv.name}: {inv.description}  scope={inv.scope}"
        )
    console.print("\n## Unknowns (honest uncertainty)")
    unknowns = ks.unknowns()
    if not unknowns:
        console.print("  (none recorded)")
    for unknown in unknowns:
        console.print("  -", unknown)


@cli.command("verify")
@click.argument("path", type=click.Path(exists=True, file_okay=False))
@click.option("--patch", type=click.Path(exists=True, dir_okay=False), required=True,
              help="Unified diff to verify.")
@click.option("--rules", type=click.Path(exists=True, dir_okay=False), required=True,
              help="JSON rule config.")
@click.option("--json-out", type=click.Path(), default=None)
@click.option("--unknown-policy", type=click.Choice(["block", "warn", "ignore"]),
              default="block", show_default=True)
@click.option("--allow-untrusted-behavioral", is_flag=True,
              help="Run untrusted behavioural snippets (only inside real isolation).")
def verify(path: str, patch: str, rules: str, json_out: str | None,
           unknown_policy: str, allow_untrusted_behavioral: bool) -> None:
    """Verify a proposed patch against architectural invariants."""
    try:
        rule_list, allow = load_rules(rules)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        _fail(f"invalid rule config {rules}: {exc}")
    try:
        patch_text = Path(patch).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        _fail(f"cannot read patch {patch}: {exc}")
    try:
        changes = ChangeSet.from_patch(patch_text, root=Path(path))
    except (ChangeError, PatchError, ValueError) as exc:
        _fail(f"invalid patch: {exc}")
    try:
        report = SemanticVerifier(
            rule_list, allow,
            unknown_policy=unknown_policy,
            allow_untrusted_behavioral=allow_untrusted_behavioral,
        ).verify(Path(path), changes)
    except (ChangeError, ValueError) as exc:
        _fail(f"verification failed: {exc}")
    console.print(verification_markdown(report))
    if json_out:
        try:
            Path(json_out).write_text(report.to_json() + "\n", encoding="utf-8")
        except OSError as exc:
            _fail(f"cannot write {json_out}: {exc}")
    if report.approved:
        raise SystemExit(0)
    raise SystemExit(3 if report.indeterminate and not report.findings else 1)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
