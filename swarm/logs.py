"""Log viewing for claude-swarm."""

import logging
import sys
import time
from pathlib import Path

logger = logging.getLogger("swarm.logs")


def get_log_dir(run_id: str) -> Path:
    """Get log directory for a run."""
    return Path(f".swarm/runs/{run_id}/logs")


def get_agent_log_path(run_id: str, agent_name: str) -> Path:
    """Get log file path for an agent."""
    return get_log_dir(run_id) / f"{agent_name}.log"


def read_log(run_id: str, agent_name: str, lines: int | None = None) -> str:
    """Read agent log file.

    Args:
        run_id: Run identifier
        agent_name: Agent name
        lines: Number of lines to read (None for all)

    Returns:
        Log content
    """
    log_path = get_agent_log_path(run_id, agent_name)

    if not log_path.exists():
        return f"Log file not found: {log_path}"

    content = log_path.read_text()

    if lines is not None:
        content_lines = content.split("\n")
        content = "\n".join(content_lines[-lines:])

    return content


def tail_log(
    run_id: str,
    agent_name: str,
    follow: bool = True,
    interval: float = 0.5,
) -> None:
    """Tail an agent log file.

    Args:
        run_id: Run identifier
        agent_name: Agent name
        follow: If True, continue following
        interval: Poll interval in seconds
    """
    log_path = get_agent_log_path(run_id, agent_name)

    if not log_path.exists():
        print(f"Log file not found: {log_path}")
        print("Waiting for log file to be created...")

        while follow and not log_path.exists():
            time.sleep(interval)

        if not log_path.exists():
            return

    # Read initial content
    with open(log_path) as f:
        content = f.read()
        sys.stdout.write(content)
        sys.stdout.flush()

        if not follow:
            return

        # Follow mode
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


def list_logs(run_id: str) -> list[str]:
    """List available log files for a run.

    Args:
        run_id: Run identifier

    Returns:
        List of agent names with logs
    """
    log_dir = get_log_dir(run_id)

    if not log_dir.exists():
        return []

    return [p.stem for p in log_dir.glob("*.log")]


def read_all_logs(run_id: str, interleaved: bool = False) -> str:
    """Read all logs for a run.

    Args:
        run_id: Run identifier
        interleaved: If True, interleave logs by timestamp

    Returns:
        Combined log content
    """
    agent_names = list_logs(run_id)

    if not agent_names:
        return "No logs found"

    if not interleaved:
        # Concatenate logs
        output = []
        for name in sorted(agent_names):
            output.append(f"\n{'='*60}\n{name}\n{'='*60}\n")
            output.append(read_log(run_id, name))
        return "".join(output)

    # Interleave by timestamp (simplified - assumes ISO timestamp prefix)
    entries = []
    for name in agent_names:
        content = read_log(run_id, name)
        for line in content.split("\n"):
            if line.strip():
                entries.append((name, line))

    # Sort by timestamp in line (if present)
    # This is a simplified implementation
    entries.sort(key=lambda x: x[1])

    return "\n".join(f"[{name}] {line}" for name, line in entries)


def setup_logging(run_id: str, verbose: bool = False) -> None:
    """Set up logging for a run.

    Args:
        run_id: Run identifier
        verbose: Enable debug logging
    """
    log_dir = get_log_dir(run_id)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger("swarm")
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    # File handler for main log
    main_log = log_dir / "swarm.log"
    file_handler = logging.FileHandler(main_log)
    file_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(levelname)-5s %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console_handler)


def log_to_agent_file(run_id: str, agent_name: str, text: str) -> None:
    """Append text to agent log file.

    Args:
        run_id: Run identifier
        agent_name: Agent name
        text: Text to append
    """
    from datetime import datetime

    log_path = get_agent_log_path(run_id, agent_name)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(log_path, "a") as f:
        timestamp = datetime.now().isoformat()
        f.write(f"[{timestamp}] {text}\n")
