"""Dependency graph + topological sort for batch plans.

Moved from the old swarm/core/deps.py. Scoped to batch because live mode's
pipelines are inherently sequential and don't need a DAG.

The graph is generic over node names — it doesn't care whether the nodes
are AgentRequest, ResolvedAgent, or raw dicts, only that each has a name
and a list of dep names.
"""

from typing import Iterator

from swarm.core.errors import PlanValidationError


class DependencyGraph:
    def __init__(self, deps: dict[str, set[str]]):
        self.deps = {name: set(d) for name, d in deps.items()}

    @classmethod
    def from_pairs(cls, pairs: list[tuple[str, list[str]]]) -> "DependencyGraph":
        return cls({name: set(deps) for name, deps in pairs})

    def ready(self, completed: set[str], failed: set[str]) -> list[str]:
        terminal = completed | failed
        return [
            name
            for name, deps in self.deps.items()
            if name not in terminal and deps.issubset(completed)
        ]

    def blocked_by_failure(self, failed: set[str]) -> list[str]:
        return [name for name, deps in self.deps.items() if deps & failed]

    def topological_order(self) -> list[str]:
        in_degree = {n: len(d) for n, d in self.deps.items()}
        queue = [n for n, d in in_degree.items() if d == 0]
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for name, deps in self.deps.items():
                if node in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        if len(order) != len(self.deps):
            raise PlanValidationError("Circular dependency detected")
        return order

    def reverse_topological_order(self) -> list[str]:
        return list(reversed(self.topological_order()))

    def dependents_of(self, name: str) -> list[str]:
        return [n for n, deps in self.deps.items() if name in deps]

    def subtree(self, root: str) -> set[str]:
        visited = {root}
        queue = [root]
        while queue:
            current = queue.pop(0)
            for dep in self.dependents_of(current):
                if dep not in visited:
                    visited.add(dep)
                    queue.append(dep)
        return visited

    def iter_layers(self) -> Iterator[list[str]]:
        remaining = set(self.deps)
        completed: set[str] = set()
        while remaining:
            layer = [n for n in remaining if self.deps[n].issubset(completed)]
            if not layer:
                raise PlanValidationError("Circular dependency detected")
            yield layer
            completed.update(layer)
            remaining -= set(layer)

    def validate(self) -> list[str]:
        errors: list[str] = []
        names = set(self.deps)
        for name, deps in self.deps.items():
            unknown = deps - names
            if unknown:
                errors.append(
                    f"Agent {name} depends on unknown agents: {sorted(unknown)}"
                )
        try:
            self.topological_order()
        except PlanValidationError:
            errors.append("Circular dependency detected")
        return errors
