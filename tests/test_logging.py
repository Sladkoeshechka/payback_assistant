import io
import json
import logging
import sys
from collections.abc import Iterator

import pytest

from payback.logging_setup import JsonFormatter, configure_logging, log_context, redact


class Sink:
    """A logger writing JSON into a buffer we own.

    Deliberately not capsys: pytest swaps sys.stdout between the setup and call
    phases, so a handler created in a fixture would write to a stream the test can
    no longer read. configure_logging's own wiring is covered separately below.
    """

    def __init__(self, name: str) -> None:
        self.buffer = io.StringIO()
        handler = logging.StreamHandler(self.buffer)
        handler.setFormatter(JsonFormatter())
        self.logger = logging.getLogger(name)
        self.logger.handlers = [handler]
        self.logger.propagate = False
        self.logger.setLevel(logging.DEBUG)

    def lines(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.buffer.getvalue().strip().splitlines()]


@pytest.fixture
def sink() -> Iterator[Sink]:
    target = Sink("payback.test")
    yield target
    target.logger.handlers.clear()


def test_each_record_is_one_json_object(sink: Sink) -> None:
    sink.logger.info("expense submitted")
    sink.logger.warning("planfix unavailable")

    lines = sink.lines()
    assert [line["message"] for line in lines] == ["expense submitted", "planfix unavailable"]
    assert [line["level"] for line in lines] == ["INFO", "WARNING"]
    assert all(line["logger"] == "payback.test" for line in lines)
    assert all("ts" in line for line in lines)


def test_extra_fields_are_included(sink: Sink) -> None:
    sink.logger.info("task created", extra={"expense_id": 7, "planfix_task_id": 36})

    (line,) = sink.lines()
    assert line["expense_id"] == 7
    assert line["planfix_task_id"] == 36


def test_context_is_bound_for_the_whole_block(sink: Sink) -> None:
    with log_context(expense_id=7):
        sink.logger.info("uploading receipt")
        with log_context(planfix_task_id=36):
            sink.logger.info("attaching file")
    sink.logger.info("done")

    first, second, third = sink.lines()
    assert first["expense_id"] == 7
    assert "planfix_task_id" not in first
    assert second["expense_id"] == 7
    assert second["planfix_task_id"] == 36
    # The context is restored on exit, so later records stay clean.
    assert "expense_id" not in third


def test_registered_secrets_are_masked(sink: Sink) -> None:
    redact("0123456789abcdef0123456789abcdef")

    sink.logger.info("calling planfix with token 0123456789abcdef0123456789abcdef")
    sink.logger.info("in a field too", extra={"token": "0123456789abcdef0123456789abcdef"})

    for line in sink.lines():
        rendered = json.dumps(line)
        assert "0123456789abcdef0123456789abcdef" not in rendered
        assert "***" in rendered


def test_secrets_inside_tracebacks_are_masked(sink: Sink) -> None:
    """The likeliest way a token escapes: an httpx error quoting the request."""
    redact("test-planfix-token")

    try:
        raise RuntimeError("401 for https://example.planfix.ru/rest?t=test-planfix-token")
    except RuntimeError:
        sink.logger.exception("planfix call failed")

    (line,) = sink.lines()
    assert "test-planfix-token" not in json.dumps(line)
    assert "RuntimeError" in str(line["exception"])


def test_short_values_are_not_masked() -> None:
    """Masking a 3-character "secret" would redact ordinary words."""
    redact("abc", None)

    record = logging.LogRecord("x", logging.INFO, "f", 1, "abc defghij", None, None)
    assert "abc" in JsonFormatter().format(record)


def test_configure_logging_installs_a_single_json_handler_on_stdout() -> None:
    try:
        configure_logging("DEBUG")

        (handler,) = logging.getLogger().handlers
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is sys.stdout
        assert isinstance(handler.formatter, JsonFormatter)
        assert logging.getLogger().level == logging.DEBUG
        # Chatty third-party loggers are turned down (spec §9).
        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        logging.getLogger().handlers.clear()
