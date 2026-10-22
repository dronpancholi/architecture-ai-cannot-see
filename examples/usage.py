"""Example: build a Knowledge Surface from the demo codebase and reason over it."""

from pathlib import Path

from knowledge_surface import (
    ChangeEvaluator,
    Confidence,
    InvariantRegistry,
    KnowledgeSurface,
    PythonASTExtractor,
)

ROOT = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
KS_OUT = Path("/tmp/ks_before.json")


def build_before() -> KnowledgeSurface:
    ks = PythonASTExtractor(ROOT).build(name="demo-before")
    # Declare the Second Architecture: the invariant that lives nowhere.
    reg = InvariantRegistry()
    order_svc = next(e for e in ks.entities() if e.name == "OrderService")
    reg.declare(
        name="credit-limit",
        description="an order's total must never exceed the customer's credit limit",
        scope=[order_svc.id],
        severity="error",
        confidence=Confidence.KNOWN,
        rationale="enforced by review culture; absent from code",
    )
    reg.apply(ks)
    return ks


if __name__ == "__main__":
    import json
    ks = build_before()
    print(ks)
    print("invariants:", [i.name for i in ks.invariants()])
    print("unknowns:", len(ks.unknowns()))
    # Evaluate removing OrderService
    ev = ChangeEvaluator(ks)
    svc = next(e for e in ks.entities() if e.name == "OrderService")
    va = ev.evaluate_remove_entity(svc.id)
    print("remove OrderService approved?", va.approved)
    print(va.verdict.summary())
    for v in va.verdict.violations:
        print("  ", v.severity, v.message)
    KS_OUT.write_text(json.dumps(ks.to_dict(), indent=2, default=str))
    print("saved", KS_OUT)
