"""YAML plan spec parsing for claude-swarm."""

import logging
import re
from pathlib import Path
from uuid import uuid4

import yaml

from swarm.models import AgentSpec, Defaults, PlanSpec

logger = logging.getLogger("swarm.parser")

MAX_HIERARCHY_DEPTH = 10


def parse_plan_file(path: Path) -> PlanSpec:
    """Parse a YAML plan file.

    Args:
        path: Path to the YAML file

    Returns:
        Parsed PlanSpec
    """
    with open(path) as f:
        content = f.read()
    return parse_plan_yaml(content)


def parse_plan_yaml(content: str) -> PlanSpec:
    """Parse YAML content into PlanSpec.

    Args:
        content: YAML content string

    Returns:
        Parsed PlanSpec
    """
    data = yaml.safe_load(content)
    return PlanSpec(**data)


def validate_plan(plan: PlanSpec) -> list[str]:
    """Validate a plan spec.

    Args:
        plan: Plan to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check for duplicate agent names
    names = [a.name for a in plan.agents]
    if len(names) != len(set(names)):
        errors.append("Duplicate agent names found")

    # Check dependencies exist
    for agent in plan.agents:
        for dep in agent.depends_on:
            if dep not in names:
                errors.append(f"Agent {agent.name} depends on unknown agent: {dep}")

    # Check for circular dependencies
    if has_circular_deps(plan.agents):
        errors.append("Circular dependency detected")

    return errors


def has_circular_deps(agents: list[AgentSpec]) -> bool:
    """Check for circular dependencies using DFS."""
    deps = {a.name: set(a.depends_on) for a in agents}

    def visit(name: str, path: set) -> bool:
        if name in path:
            return True
        path.add(name)
        for dep in deps.get(name, []):
            if visit(dep, path):
                return True
        path.remove(name)
        return False

    for agent in agents:
        if visit(agent.name, set()):
            return True
    return False


def infer_agent_name(prompt: str) -> str:
    """Extract key term from prompt for agent name.

    Args:
        prompt: Agent prompt

    Returns:
        Inferred name
    """
    # Common patterns: "Implement X", "Add X", "Fix X", "Refactor X"
    patterns = [
        r"(?:implement|add|create|build)\s+(\w+)",
        r"(?:fix|resolve|debug)\s+(\w+)",
        r"(?:refactor|update|improve)\s+(\w+)",
    ]
    for pattern in patterns:
        if match := re.search(pattern, prompt, re.I):
            return match.group(1).lower()

    # Fallback: first significant word
    words = [w for w in prompt.split() if len(w) > 3]
    return words[0].lower() if words else f"task-{uuid4().hex[:6]}"


def parse_inline_agents(prompts: list[str]) -> list[AgentSpec]:
    """Parse inline agent definitions from -p flags.

    Supports formats:
    - "name: prompt" - explicit name
    - "prompt" - name inferred from prompt

    Args:
        prompts: List of prompt strings

    Returns:
        List of AgentSpec
    """
    agents = []

    for prompt in prompts:
        if ":" in prompt and not prompt.startswith("http"):
            # "name: prompt" format
            name, rest = prompt.split(":", 1)
            name = name.strip()
            prompt_text = rest.strip()
        else:
            # Infer name from prompt
            name = infer_agent_name(prompt)
            prompt_text = prompt

        agents.append(AgentSpec(name=name, prompt=prompt_text))

    return agents


def create_inline_plan(
    prompts: list[str],
    sequential: bool = False,
    defaults: Defaults | None = None,
) -> PlanSpec:
    """Create a plan from inline prompts.

    Args:
        prompts: List of prompt strings
        sequential: If True, agents depend on previous
        defaults: Default settings

    Returns:
        PlanSpec
    """
    agents = parse_inline_agents(prompts)

    # Add sequential dependencies if requested
    if sequential and len(agents) > 1:
        for i in range(1, len(agents)):
            agents[i].depends_on = [agents[i - 1].name]

    return PlanSpec(
        name=f"inline-{uuid4().hex[:8]}",
        defaults=defaults or Defaults(),
        agents=agents,
    )


def expand_pattern_agents(
    pattern: str,
    prompt_template: str,
    base_path: Path | None = None,
) -> list[AgentSpec]:
    """Expand a glob pattern to multiple agents.

    Args:
        pattern: Glob pattern (e.g., "src/services/*.py")
        prompt_template: Prompt template with {file} placeholder
        base_path: Base path for glob

    Returns:
        List of AgentSpec, one per matched file
    """
    base = base_path or Path.cwd()
    files = list(base.glob(pattern))

    agents = []
    for file in files:
        name = file.stem.lower().replace("_", "-")
        prompt = prompt_template.format(file=str(file))
        agents.append(AgentSpec(name=name, prompt=prompt))

    return agents


def generate_run_id(plan_name: str) -> str:
    """Generate a unique run ID.

    Args:
        plan_name: Name of the plan

    Returns:
        Run ID string
    """
    return f"{plan_name}-{uuid4().hex[:8]}"


def load_shared_context(paths: list[str], base_path: Path | None = None) -> str:
    """Load shared context files.

    Args:
        paths: List of file paths
        base_path: Base path for relative paths

    Returns:
        Combined content string
    """
    base = base_path or Path.cwd()
    contents = []

    for path in paths:
        full_path = base / path
        if full_path.exists():
            contents.append(f"--- {path} ---\n{full_path.read_text()}")
        else:
            logger.warning(f"Shared context file not found: {path}")

    return "\n\n".join(contents)
