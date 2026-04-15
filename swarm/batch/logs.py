"""Per-agent log file helpers for batch runs.

Logs stay as plain files (one per agent) so `tail -f` still works. The
SqliteSink in batch/sqlite.py forwards LogText events through
append_agent_log so both the events table and the log file stay consistent.
"""

import sys
import time
from pathlib import Path

from swarm.batch.sqlite import ensure_log_file, get_log_path, get_logs_dir


def read_log(
    run_id: str,
    agent_name: str,
    lines: int | None = None,
    base_path: Path | None = None,
) -> str:
    log_path = get_log_path(run_id, agent_name, base_path)
    if not log_path.exists():
        return f"Log file not found: {log_path}"
    content = log_path.read_text()
    if lines is not None:
        content = "\n".join(content.split("\n")[-lines:])
    return content


def tail_log(
    run_id: str,
    agent_name: str,
    follow: bool = True,
    interval: float = 0.5,
    base_path: Path | None = None,
) -> None:
    log_path = get_log_path(run_id, agent_name, base_path)
    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        print("Waiting for log file to be created...")
        while follow and not log_path.exists():
            time.sleep(interval)
        if not log_path.exists():
            return
    with open(log_path) as f:
        sys.stdout.write(f.read())
        sys.stdout.flush()
        if not follow:
            return
        try:
            while True:
                line = f.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(interval)
        except KeyboardInterrupt:
            print("\n")


def list_logs(run_id: str, base_path: Path | None = None) -> list[str]:
    log_dir = get_logs_dir(run_id, base_path)
    if not log_dir.exists():
        return []
    return sorted(p.stem for p in log_dir.glob("*.log"))


def read_all_logs(run_id: str, base_path: Path | None = None) -> str:
    names = list_logs(run_id, base_path)
    if not names:
        return "No logs found"
    output = []
    for name in names:
        output.append(f"\n{'=' * 60}\n{name}\n{'=' * 60}\n")
        output.append(read_log(run_id, name, base_path=base_path))
    return "".join(output)


def append_agent_log(
    run_id: str,
    agent_name: str,
    text: str,
    base_path: Path | None = None,
) -> None:
    log_path = ensure_log_file(run_id, agent_name, base_path)
    with open(log_path, "a") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")
