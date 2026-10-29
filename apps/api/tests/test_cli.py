import json
import sys

import pytest


def test_cli_hides_unexpected_exception_details(monkeypatch, capsys):
    from app import cli

    async def fail(args):
        raise RuntimeError("secret-sentinel")

    monkeypatch.setattr(cli, "execute", fail)
    monkeypatch.setattr(sys, "argv", ["maintenance", "stats"])
    assert cli.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["error"] == "INTERNAL_ERROR"
    assert "secret-sentinel" not in output


def test_human_and_delegated_ai_confirmation_cannot_be_combined():
    from app.cli import parser

    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "publish",
                "--version",
                "00000000-0000-0000-0000-000000000001",
                "--reviewer",
                "ai:codex",
                "--confirm-human-review",
                "--confirm-delegated-ai-review",
            ]
        )
