from __future__ import annotations

import io
import logging

import pytest

from remote_ops_workspace import cli, logging_setup


def test_resolve_log_level_uses_explicit_env_and_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ROW_LOG_LEVEL", raising=False)
    assert logging_setup.resolve_log_level(None) == "WARNING"
    assert logging_setup.resolve_log_level("debug") == "DEBUG"

    monkeypatch.setenv("ROW_LOG_LEVEL", " info ")
    assert logging_setup.resolve_log_level(None) == "INFO"

    monkeypatch.setenv("ROW_LOG_LEVEL", "bogus")
    with pytest.raises(ValueError, match="unsupported log level"):
        logging_setup.resolve_log_level(None)


def test_configure_logging_installs_a_redacting_handler() -> None:
    stream = io.StringIO()
    logger = logging_setup.configure_logging("INFO", stream=stream)
    assert logging_setup.configure_logging("DEBUG", stream=stream) is logger
    assert logger.level == logging.DEBUG
    assert logger.propagate is False
    assert len(logger.handlers) == 1

    logging_setup.diagnostic_logger("web").info(
        "connecting to postgres://app:s3cr3t@db.example/row"
    )
    output = stream.getvalue()
    assert "s3cr3t" not in output
    assert "***REDACTED***" in output

    default_stream_logger = logging_setup.configure_logging("WARNING")
    assert default_stream_logger is logger
    logging_setup.configure_logging("WARNING", stream=io.StringIO())


def test_cli_main_reports_invalid_environment_log_level(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("ROW_LOG_LEVEL", "verbose")
    assert cli.main(["doctor", "--json"]) == 2
    assert "unsupported log level" in capsys.readouterr().err

    monkeypatch.delenv("ROW_LOG_LEVEL", raising=False)
    assert cli.main(["--log-level", "ERROR", "doctor", "--json"]) in (0, 1)
