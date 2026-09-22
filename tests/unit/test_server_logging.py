"""The site's logging: what a record carries, and what never reaches one."""

import json
import logging
import logging.config

import pytest

from server.config import Config, ConfigError
from server.logging import (
    DEFAULT_LEVEL,
    JsonFormatter,
    RequestIdFilter,
    known_level,
    log_config,
    request_id,
)


def record(
    level: int = logging.INFO, message: str = "hello", **extra
) -> logging.LogRecord:
    made = logging.LogRecord(
        "server.test", level, "server/test.py", 1, message, (), None
    )
    for name, value in extra.items():
        setattr(made, name, value)
    RequestIdFilter().filter(made)
    return made


def formatted(**kwargs) -> dict:
    return json.loads(JsonFormatter().format(record(**kwargs)))


# -- What a record carries ----------------------------------------------------------------


def test_a_record_is_one_json_object():
    fields = formatted()
    assert fields["level"] == "INFO"
    assert fields["logger"] == "server.test"
    assert fields["msg"] == "hello"
    assert fields["ts"].endswith("Z")


def test_extra_fields_land_beside_the_message():
    assert formatted(seed="abc", slot=0)["seed"] == "abc"


def test_a_record_carries_the_request_it_happened_in():
    token = request_id.set("deadbeefdeadbeef")
    try:
        assert formatted()["request_id"] == "deadbeefdeadbeef"
    finally:
        request_id.reset(token)


def test_a_record_outside_a_request_carries_no_id():
    assert formatted()["request_id"] == ""


def test_a_value_json_cannot_serialize_becomes_its_repr():
    """A field logging cannot encode is worth its repr, never a lost record."""
    assert "frozenset" in formatted(settings=frozenset({"a"}))["settings"]


def test_an_exception_brings_its_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        made = record()
        made.exc_info = sys.exc_info()
        fields = json.loads(JsonFormatter().format(made))
    assert "ValueError: boom" in fields["exc"]


# -- The configuration --------------------------------------------------------------------


def test_the_root_logger_is_the_one_that_is_configured():
    assert log_config("INFO")["root"]["handlers"] == ["stderr"]


def test_uvicorns_access_log_is_off_because_caddy_keeps_it():
    assert log_config("INFO")["loggers"]["uvicorn.access"]["propagate"] is False


def test_the_level_is_taken_as_given_in_any_case():
    assert log_config("debug")["root"]["level"] == "DEBUG"


def test_loggers_made_before_the_configuration_keep_working():
    """server.submissions holds its logger from import time."""
    assert log_config("INFO")["disable_existing_loggers"] is False


@pytest.mark.parametrize("level", ["DEBUG", "info", "WARNING", "error", "CRITICAL"])
def test_a_level_name_is_known(level):
    assert known_level(level)


def test_a_level_that_is_not_a_level_is_refused_at_startup():
    with pytest.raises(ConfigError):
        Config(log_level="chatty").validate()


def test_the_default_level_is_a_level():
    assert known_level(DEFAULT_LEVEL)
    Config().validate()


# -- What never reaches a record ----------------------------------------------------------


def test_info_records_survive_the_configuration(capsys):
    """Without a configuration the root logger has no handler and INFO is discarded."""
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        logging.config.dictConfig(log_config("INFO"))
        logging.getLogger("server.test").info("kept", extra={"seed": "abc"})
        written = capsys.readouterr().err
    finally:
        root.handlers[:], root.level = saved
    fields = json.loads(written)
    assert fields["msg"] == "kept"
    assert fields["seed"] == "abc"
