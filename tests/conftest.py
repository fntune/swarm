"""Shared fixtures: per-test working directory + adapter registration."""

import os
from pathlib import Path

import pytest

# Register adapters once per test session.
import swarm.adapters.claude  # noqa: F401
import swarm.adapters.mock  # noqa: F401
import swarm.adapters.openai  # noqa: F401


@pytest.fixture
def cwd_tmp(tmp_path: Path):
    """Run a test in an isolated cwd so .swarm/ artifacts don't bleed."""
    prev = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(prev)


@pytest.fixture(autouse=True)
def clean_default_runtime_env(monkeypatch):
    monkeypatch.delenv("SWARM_DEFAULT_RUNTIME", raising=False)
