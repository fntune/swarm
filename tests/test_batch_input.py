"""YAML parsing + inline plan building + validation."""

import pytest

from swarm.batch.input import (
    build_inline_plan,
    infer_agent_name,
    parse_inline_agents,
    parse_plan_yaml,
)
from swarm.core.errors import PlanValidationError


def test_parse_plan_yaml_minimal():
    plan = parse_plan_yaml(
        """
name: tiny
agents:
  - name: a
    prompt: do a
  - name: b
    prompt: do b
    depends_on: [a]
    profile: tester
"""
    )
    assert plan.name == "tiny"
    assert [a.name for a in plan.agents] == ["a", "b"]
    assert plan.agents[1].depends_on == ("a",)
    assert plan.agents[1].profile == "tester"


def test_parse_plan_yaml_validates_cycle():
    with pytest.raises(PlanValidationError):
        parse_plan_yaml(
            """
name: cycle
agents:
  - name: a
    prompt: x
    depends_on: [b]
  - name: b
    prompt: y
    depends_on: [a]
"""
        )


def test_parse_plan_yaml_validates_duplicate():
    with pytest.raises(PlanValidationError):
        parse_plan_yaml(
            """
name: dup
agents:
  - name: x
    prompt: a
  - name: x
    prompt: b
"""
        )


def test_inline_plan_named_prompts():
    plan = build_inline_plan(["auth: implement auth", "tests: write tests"])
    assert [a.name for a in plan.agents] == ["auth", "tests"]


def test_inline_plan_sequential_chains_deps():
    plan = build_inline_plan(
        ["a: do a", "b: do b", "c: do c"], sequential=True
    )
    assert plan.agents[0].depends_on == ()
    assert plan.agents[1].depends_on == ("a",)
    assert plan.agents[2].depends_on == ("b",)


def test_infer_agent_name_action_pattern():
    assert infer_agent_name("Implement login flow") == "login"
    assert infer_agent_name("Fix parser bug") == "parser"
    assert infer_agent_name("Refactor scheduler") == "scheduler"


def test_parse_inline_agents_anonymous():
    agents = parse_inline_agents(["Implement caching layer"])
    assert agents[0].name == "caching"
