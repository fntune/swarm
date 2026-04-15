"""Profile registry and capability shape."""

from swarm.core.capabilities import Capability, DEFAULT_CODING_CAPS, READONLY_CAPS
from swarm.core.profiles import PROFILE_REGISTRY, get_profile, list_profiles


def test_eight_builtin_profiles_registered():
    assert set(list_profiles()) == {
        "implementer",
        "architect",
        "tester",
        "reviewer",
        "debugger",
        "refactorer",
        "documenter",
        "orchestrator",
    }


def test_reviewer_is_read_only_with_shell():
    p = get_profile("reviewer")
    assert p.read_only is True
    assert p.capabilities == READONLY_CAPS
    assert Capability.SHELL in p.capabilities
    assert Capability.FILE_WRITE not in p.capabilities
    assert Capability.FILE_EDIT not in p.capabilities


def test_implementer_default_caps():
    p = get_profile("implementer")
    assert p.read_only is False
    assert p.capabilities == DEFAULT_CODING_CAPS


def test_orchestrator_has_supervisor_ops():
    p = get_profile("orchestrator")
    assert "spawn" in p.coord_ops
    assert "status" in p.coord_ops
    assert "respond" in p.coord_ops
    assert "mark_plan_complete" in p.coord_ops
    assert p.capabilities == DEFAULT_CODING_CAPS
