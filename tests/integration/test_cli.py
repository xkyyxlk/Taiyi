from __future__ import annotations

import json

from typer.testing import CliRunner

from taiyi.cli.app import app

runner = CliRunner()


def test_cli_minimal_workflow(tmp_path) -> None:  # type: ignore[no-untyped-def]
    options = ["--data-dir", str(tmp_path)]
    assert runner.invoke(app, [*options, "--help"]).exit_code == 0
    initialized = runner.invoke(app, [*options, "init", "Taiyi"])
    assert initialized.exit_code == 0, initialized.output
    duplicate = runner.invoke(app, [*options, "init", "Another"])
    assert duplicate.exit_code == 1
    assert runner.invoke(app, [*options, "fork", "alpha"]).exit_code == 0
    chat = runner.invoke(app, [*options, "chat", "alpha", "hello"])
    assert chat.exit_code == 0, chat.output
    shown = runner.invoke(app, [*options, "worldline", "show", "alpha"])
    assert shown.exit_code == 0
    assert len(json.loads(shown.output)) == 3
