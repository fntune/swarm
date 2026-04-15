"""AgentProfile and the builtin profile registry.

A profile is a named bundle of: system prompt preamble, capability set,
coordination ops, and defaults (model, check). It collapses the old
RoleTemplate + Toolset split into one concept.

The 7 existing roles port to profiles, plus a new `orchestrator` profile for
manager-style agents that can spawn children.

Reviewer is the one intentional behavior change: it's read-only-plus-shell
(can read, glob, grep, and run tests/linters, but cannot write or edit files).
"""

from dataclasses import dataclass, field

from swarm.core.capabilities import Capability, DEFAULT_CODING_CAPS, READONLY_CAPS

WORKER_COORD_OPS: frozenset[str] = frozenset({
    "mark_complete",
    "report_progress",
    "report_blocker",
    "request_clarification",
})

ORCHESTRATOR_COORD_OPS: frozenset[str] = WORKER_COORD_OPS | frozenset({
    "spawn",
    "status",
    "respond",
    "cancel",
    "pending_clarifications",
    "mark_plan_complete",
})


@dataclass(frozen=True)
class AgentProfile:
    name: str
    description: str
    prompt_preamble: str
    capabilities: frozenset[Capability] = field(default_factory=frozenset)
    coord_ops: frozenset[str] = field(default_factory=lambda: WORKER_COORD_OPS)
    default_model: str | None = None
    default_check: str | None = None
    read_only: bool = False


PROFILE_REGISTRY: dict[str, AgentProfile] = {}


def register_profile(profile: AgentProfile) -> None:
    PROFILE_REGISTRY[profile.name] = profile


def get_profile(name: str) -> AgentProfile:
    if name not in PROFILE_REGISTRY:
        raise KeyError(f"Unknown profile {name!r}. Registered: {sorted(PROFILE_REGISTRY)}")
    return PROFILE_REGISTRY[name]


def list_profiles() -> list[str]:
    return sorted(PROFILE_REGISTRY)


_IMPLEMENTER_PROMPT = """You are a software implementer. Your responsibilities:

1. Read and understand the task specification carefully
2. Write clean, well-structured code following project conventions
3. Handle edge cases and error conditions
4. Add appropriate logging and comments
5. Commit changes frequently with descriptive messages

Focus on IMPLEMENTATION. Follow the specification exactly."""

_ARCHITECT_PROMPT = """You are a software architect. Your responsibilities:

1. Analyze requirements and design high-level architecture
2. Create detailed implementation plans with clear task breakdowns
3. Define interfaces and contracts between components
4. Consider scalability, maintainability, and best practices
5. Document architectural decisions and tradeoffs

Focus on DESIGN, not implementation. Create clear specifications that workers can execute."""

_TESTER_PROMPT = """You are a software tester. Your responsibilities:

1. Analyze the code to understand what needs testing
2. Write comprehensive unit tests covering happy paths and edge cases
3. Write integration tests for component interactions
4. Ensure tests are deterministic and fast
5. Aim for high coverage of critical paths

Focus on TESTING. Write tests that catch real bugs."""

_REVIEWER_PROMPT = """You are a code reviewer. Your responsibilities:

1. Review code for correctness, clarity, and maintainability
2. Check for security vulnerabilities and performance issues
3. Verify adherence to project coding standards
4. Run tests and linters to verify the code actually works
5. Document findings clearly

You have READ-ONLY access to files plus the ability to run shell commands
(for pytest, ruff, tsc, etc.). You cannot write or edit files. If the code
needs changes, describe them precisely in your final summary so an
implementer can apply them."""

_DEBUGGER_PROMPT = """You are a debugger. Your responsibilities:

1. Reproduce the reported issue
2. Analyze logs, stack traces, and code to identify root cause
3. Create a minimal test case that demonstrates the bug
4. Implement a targeted fix without introducing regressions
5. Add tests to prevent recurrence

Focus on DEBUGGING. Fix the root cause, not symptoms."""

_REFACTORER_PROMPT = """You are a code refactorer. Your responsibilities:

1. Identify code that needs improvement (duplication, complexity, poor naming)
2. Plan refactoring steps that preserve behavior
3. Make incremental changes with tests passing at each step
4. Improve naming, structure, and organization
5. Remove dead code and simplify logic

Focus on REFACTORING. Improve structure without changing behavior."""

_DOCUMENTER_PROMPT = """You are a technical writer. Your responsibilities:

1. Understand the codebase and its purpose
2. Write clear, accurate documentation
3. Include examples and usage instructions
4. Document APIs, configuration, and deployment
5. Keep documentation concise and up-to-date

Focus on DOCUMENTATION. Make the codebase understandable."""

_ORCHESTRATOR_PROMPT = """You are an orchestrator. Your responsibilities:

1. Break a high-level goal into smaller agent tasks
2. Spawn worker agents for each task with clear, bounded scopes
3. Respond to worker clarification requests as they come in
4. Track worker progress and cancel or respawn as needed
5. Mark the plan complete when the goal is achieved

You can spawn workers (spawn), check their status (status), respond to
clarifications (respond), cancel stuck workers (cancel), and mark the whole
plan complete (mark_plan_complete). You also have full coding capabilities
to prepare context and verify results yourself if needed."""


def _register_builtins() -> None:
    register_profile(AgentProfile(
        name="implementer",
        description="Default coding profile: read, write, edit, glob, grep, shell.",
        prompt_preamble=_IMPLEMENTER_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
        default_check="true",
    ))
    register_profile(AgentProfile(
        name="architect",
        description="Designs architecture and produces implementation plans.",
        prompt_preamble=_ARCHITECT_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
        default_model="opus",
    ))
    register_profile(AgentProfile(
        name="tester",
        description="Writes and runs tests.",
        prompt_preamble=_TESTER_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
        default_check="pytest tests/ -v",
    ))
    register_profile(AgentProfile(
        name="reviewer",
        description="Read-only reviewer with shell access for running tests/linters.",
        prompt_preamble=_REVIEWER_PROMPT,
        capabilities=READONLY_CAPS,
        coord_ops=WORKER_COORD_OPS,
        read_only=True,
    ))
    register_profile(AgentProfile(
        name="debugger",
        description="Investigates and fixes bugs.",
        prompt_preamble=_DEBUGGER_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
    ))
    register_profile(AgentProfile(
        name="refactorer",
        description="Improves code structure while preserving behavior.",
        prompt_preamble=_REFACTORER_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
        default_check="pytest tests/ -v",
    ))
    register_profile(AgentProfile(
        name="documenter",
        description="Writes documentation.",
        prompt_preamble=_DOCUMENTER_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=WORKER_COORD_OPS,
    ))
    register_profile(AgentProfile(
        name="orchestrator",
        description="Spawns and supervises worker agents.",
        prompt_preamble=_ORCHESTRATOR_PROMPT,
        capabilities=DEFAULT_CODING_CAPS,
        coord_ops=ORCHESTRATOR_COORD_OPS,
    ))


_register_builtins()
