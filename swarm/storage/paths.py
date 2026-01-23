"""Path helpers for claude-swarm."""

from pathlib import Path


def get_run_dir(run_id: str, base_path: Path | None = None) -> Path:
    """Get the run directory for a run."""
    base = base_path or Path.cwd()
    return base / ".swarm" / "runs" / run_id


def get_db_path(run_id: str, base_path: Path | None = None) -> Path:
    """Get the database path for a run."""
    return get_run_dir(run_id, base_path) / "swarm.db"


def get_logs_dir(run_id: str, base_path: Path | None = None) -> Path:
    """Get the logs directory for a run."""
    return get_run_dir(run_id, base_path) / "logs"


def get_worktrees_dir(run_id: str, base_path: Path | None = None) -> Path:
    """Get the worktrees directory for a run."""
    return get_run_dir(run_id, base_path) / "worktrees"


def get_log_path(run_id: str, agent_name: str, base_path: Path | None = None) -> Path:
    """Get the log file path for an agent."""
    return get_logs_dir(run_id, base_path) / f"{agent_name}.log"


def ensure_log_file(run_id: str, agent_name: str, base_path: Path | None = None) -> Path:
    """Get or create log file path for an agent."""
    log_path = get_log_path(run_id, agent_name, base_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path
