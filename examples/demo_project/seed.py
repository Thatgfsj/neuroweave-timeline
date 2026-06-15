"""Seed a demo project timeline.

Run with::

    python examples/demo_project/seed.py /tmp/nwt-demo

After this, ``/tmp/nwt-demo/.nwt/`` contains a small but realistic
timeline you can explore with the CLI:

    nwt --root /tmp/nwt-demo history
    nwt --root /tmp/nwt-demo graph
    nwt --root /tmp/nwt-demo story
    nwt --root /tmp/nwt-demo explain activation.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Make the in-repo `nwt` package importable when this file is run directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nwt.core.relations import Relation
from nwt.storage.layout import init_workspace
from nwt.timeline import engine as timeline


def seed(target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    init_workspace(target, project_name="memory-engine-demo")

    e1 = timeline.create_event(
        task="Project scaffolded",
        summary="Set up package layout and CLI",
        reason="Kickoff the MVP",
        files=["pyproject.toml", "README.md"],
        tags=["setup", "milestone"],
        root=target,
    )
    e2 = timeline.create_event(
        task="Add memory engine",
        summary="In-memory graph store with id-keyed nodes",
        reason="Need a place to put things",
        files=["memory.py"],
        tags=["core", "milestone"],
        parent=e1.id,
        root=target,
    )
    e3 = timeline.create_event(
        task="Add activation spreading",
        summary="Walk the graph and decay node activations",
        reason="Retrieval was sequential and slow",
        files=["activation.py", "retriever.py"],
        tags=["memory", "optimization"],
        parent=e2.id,
        root=target,
    )
    e4 = timeline.create_event(
        task="Add decay mechanism",
        summary="Multiply activations by a per-step factor",
        reason="Stale nodes should fade",
        files=["activation.py"],
        tags=["memory"],
        parent=e2.id,
        root=target,
    )
    e5 = timeline.create_event(
        task="Vectorize activation",
        summary="Use numpy batched scoring",
        reason="Loop was the hot path in profiling",
        files=["activation.py"],
        tags=["refactor", "performance"],
        parent=e3.id,
        root=target,
    )

    # Add typed edges.
    timeline.link(e2.id, e3.id, Relation.EXTENDS, root=target)
    timeline.link(e4.id, e5.id, Relation.FIXES, root=target)

    print(f"seeded {5} events at {target / '.nwt'}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/nwt-demo")
    seed(out)
