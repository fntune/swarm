"""Claude capability -> tool name mapping."""

from swarm.adapters.claude.builtins import expand_tools
from swarm.adapters.claude.tools import allowed_coord_tool_names
from swarm.core.capabilities import (
    Capability,
    DEFAULT_CODING_CAPS,
    READONLY_CAPS,
)
from swarm.core.profiles import get_profile


def test_default_caps_expand_to_six_tools():
    assert expand_tools(DEFAULT_CODING_CAPS) == [
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "Bash",
    ]


def test_readonly_caps_keep_bash():
    assert expand_tools(READONLY_CAPS) == ["Read", "Glob", "Grep", "Bash"]
    # Sanity: no write/edit
    assert "Write" not in expand_tools(READONLY_CAPS)
    assert "Edit" not in expand_tools(READONLY_CAPS)


def test_empty_caps():
    assert expand_tools(frozenset()) == []


def test_single_cap():
    assert expand_tools(frozenset({Capability.SHELL})) == ["Bash"]


def test_orchestrator_coord_tool_names():
    profile = get_profile("orchestrator")
    names = allowed_coord_tool_names(profile.coord_ops)
    assert "mcp__swarm__spawn_worker" in names
    assert "mcp__swarm__mark_plan_complete" in names
    # Worker-side ops also present because orchestrator inherits them
    assert "mcp__swarm__mark_complete" in names


def test_reviewer_coord_tool_names_excludes_spawn():
    profile = get_profile("reviewer")
    names = allowed_coord_tool_names(profile.coord_ops)
    assert "mcp__swarm__spawn_worker" not in names
    assert "mcp__swarm__mark_complete" in names
