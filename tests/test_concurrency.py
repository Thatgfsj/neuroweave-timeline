"""Concurrency regressions.

Red-team finding: the id lock protected the counter only — concurrent
``nwt log`` processes crashed on the unlocked index rewrite (Windows
PermissionError on the atomic rename) and silently lost index entries,
so searches returned wrong results. Index updates are now serialized by
``.nwt/indices/.lock``; these tests keep that honest.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from nwt.storage.indices import IndexStore
from nwt.storage.layout import open_workspace
from nwt.storage.reader import read_all_events

REPO = Path(__file__).resolve().parents[1]


def test_next_id_unique_across_processes(
    tmp_path: Path, project_root: Path
) -> None:
    counter = project_root / ".nwt" / ".counter.json"
    script = tmp_path / "alloc.py"
    script.write_text(
        "import sys\n"
        f"sys.path.insert(0, r'{REPO}')\n"
        "from nwt.core.ids import next_id\n"
        f"ids = [next_id(r'{counter}') for _ in range(25)]\n"
        "print('\\n'.join(ids))\n",
        encoding="utf-8",
    )
    procs = [
        subprocess.Popen(
            [sys.executable, str(script)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for _ in range(4)
    ]
    all_ids: list[str] = []
    for p in procs:
        out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
        all_ids.extend(line for line in out.splitlines() if line.strip())
    assert len(all_ids) == 100
    assert len(set(all_ids)) == 100


def test_concurrent_log_no_crash_and_no_index_loss(project_root: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    procs = [
        subprocess.Popen(
            [
                sys.executable, "-m", "nwt.cli.main", "--root", str(project_root),
                "log", f"t{i}", "--files", "shared.py", "--tags", "shared",
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
        )
        for i in range(6)
    ]
    for p in procs:
        _out, err = p.communicate(timeout=120)
        assert p.returncode == 0, err  # used to PermissionError on Windows

    ws = open_workspace(project_root)
    events = read_all_events(ws)
    assert len(events) == 6
    assert len({e.id for e in events}) == 6

    store = IndexStore(ws)
    assert sorted(store.by_file("shared.py")) == sorted(e.id for e in events)
    assert len(store.by_tag("shared")) == 6
