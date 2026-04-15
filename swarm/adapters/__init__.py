"""Vendor adapters.

Each subpackage (claude, openai, mock) owns its executor, tool wrappers,
and capability map. Importing a subpackage registers its executor via
swarm.core.execution.register.
"""
