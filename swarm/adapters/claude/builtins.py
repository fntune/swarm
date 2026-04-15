"""Capability -> Claude tool name mapping.

The mapping is stable and deterministic: given a capability set, we emit
a canonically-ordered list of Claude tool names that the ClaudeAgentOptions
allowed_tools field accepts.
"""

from swarm.core.capabilities import CANONICAL_CAPABILITY_ORDER, Capability

CLAUDE_CAPABILITY_MAP: dict[Capability, tuple[str, ...]] = {
    Capability.FILE_READ: ("Read",),
    Capability.FILE_WRITE: ("Write",),
    Capability.FILE_EDIT: ("Edit",),
    Capability.GLOB: ("Glob",),
    Capability.GREP: ("Grep",),
    Capability.SHELL: ("Bash",),
    Capability.WEB_FETCH: ("WebFetch",),
    Capability.WEB_SEARCH: ("WebSearch",),
}


def expand_tools(capabilities: frozenset[Capability]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for cap in CANONICAL_CAPABILITY_ORDER:
        if cap not in capabilities:
            continue
        for tool_name in CLAUDE_CAPABILITY_MAP.get(cap, ()):
            if tool_name not in seen:
                out.append(tool_name)
                seen.add(tool_name)
    return out
