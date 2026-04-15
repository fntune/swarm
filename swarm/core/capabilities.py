"""Capability enum and canonical ordering.

A capability is an abstract permission — `FILE_READ`, `SHELL`, etc. — that
adapters translate into their vendor's concrete tool names. The plan spec and
profiles deal only in Capability; the Claude adapter maps them to
`Read`/`Write`/... and the OpenAI adapter wires them to `@function_tool`s.

Keeping capabilities abstract means the same profile works on both vendors
without leaking Claude tool names through the core.
"""

from enum import Enum


class Capability(str, Enum):
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_EDIT = "file_edit"
    GLOB = "glob"
    GREP = "grep"
    SHELL = "shell"
    WEB_FETCH = "web_fetch"
    WEB_SEARCH = "web_search"


CANONICAL_CAPABILITY_ORDER: tuple[Capability, ...] = (
    Capability.FILE_READ,
    Capability.FILE_WRITE,
    Capability.FILE_EDIT,
    Capability.GLOB,
    Capability.GREP,
    Capability.SHELL,
    Capability.WEB_FETCH,
    Capability.WEB_SEARCH,
)

DEFAULT_CODING_CAPS: frozenset[Capability] = frozenset({
    Capability.FILE_READ,
    Capability.FILE_WRITE,
    Capability.FILE_EDIT,
    Capability.GLOB,
    Capability.GREP,
    Capability.SHELL,
})

READONLY_CAPS: frozenset[Capability] = frozenset({
    Capability.FILE_READ,
    Capability.GLOB,
    Capability.GREP,
    Capability.SHELL,
})
