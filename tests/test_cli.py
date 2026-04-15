"""CLI smoke tests via click.CliRunner."""

import json

from click.testing import CliRunner

from swarm.cli import main


def test_help_shows_all_commands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for cmd in [
        "run",
        "resume",
        "status",
        "logs",
        "merge",
        "cancel",
        "dashboard",
        "clean",
        "db",
        "profiles",
    ]:
        assert cmd in result.output
    # Renamed: roles is gone
    assert "roles" not in result.output


def test_roles_command_does_not_exist():
    result = CliRunner().invoke(main, ["roles"])
    assert result.exit_code != 0
    assert "No such command" in result.output or "Usage" in result.output


def test_profiles_lists_eight():
    result = CliRunner().invoke(main, ["profiles"])
    assert result.exit_code == 0
    for name in [
        "implementer",
        "architect",
        "tester",
        "reviewer",
        "debugger",
        "refactorer",
        "documenter",
        "orchestrator",
    ]:
        assert name in result.output
    assert "[read-only]" in result.output  # reviewer marked read-only


def test_profiles_detail_for_reviewer():
    result = CliRunner().invoke(main, ["profiles", "reviewer"])
    assert result.exit_code == 0
    assert "Read-only: True" in result.output
    assert "shell" in result.output  # SHELL capability listed
    assert "file_write" not in result.output


def test_profiles_unknown_aborts():
    result = CliRunner().invoke(main, ["profiles", "bogus"])
    assert result.exit_code != 0


def test_run_inline_mock(cwd_tmp):
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["run", "-p", "test: write nothing", "--mock"],
    )
    assert result.exit_code == 0, result.output
    assert "Success: True" in result.output


def test_run_requires_file_or_prompt():
    result = CliRunner().invoke(main, ["run"])
    assert result.exit_code != 0
    assert "--file" in result.output or "--prompt" in result.output


def test_status_json_after_run(cwd_tmp):
    runner = CliRunner()
    runner.invoke(main, ["run", "-p", "t: noop", "--mock"])
    result = runner.invoke(main, ["status", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "run_id" in payload
    assert payload["nodes"]
    assert payload["nodes"][0]["status"] == "completed"


def test_clean_removes_run(cwd_tmp):
    runner = CliRunner()
    runner.invoke(main, ["run", "-p", "t: noop", "--mock"])
    runs = (cwd_tmp / ".swarm" / "runs").glob("*")
    run_id = next(iter(runs)).name
    result = runner.invoke(main, ["clean", run_id])
    assert result.exit_code == 0
    assert not (cwd_tmp / ".swarm" / "runs" / run_id).exists()
