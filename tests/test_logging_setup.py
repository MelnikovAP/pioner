"""Tests for the per-session logging setup (P1-40)."""

import logging

import pytest

from pioner.shared.logging_setup import (
    SESSION_LOG_TIMESTAMP_FORMAT,
    configure_logging,
    session_log_filename,
)

_FLAG = "_pioner_session_handler"


def _session_handlers():
    return [h for h in logging.getLogger().handlers if getattr(h, _FLAG, False)]


@pytest.fixture(autouse=True)
def _cleanup_session_handlers():
    """Remove any session handlers this module installs, before and after a test,
    so the global root logger / open file handles never leak across tests."""
    def drop():
        for h in _session_handlers():
            logging.getLogger().removeHandler(h)
            h.close()
    drop()
    yield
    drop()


def test_creates_session_file_and_writes(tmp_path):
    path = configure_logging(log_dir=str(tmp_path), timestamp="2026-06-09_14-30-05")
    assert path.name == "pioner_session_2026-06-09_14-30-05.log"
    assert path.exists()
    logging.getLogger("pioner.test").info("marker-abc-123")
    for h in _session_handlers():
        h.flush()
    assert "marker-abc-123" in path.read_text()


def test_filename_is_filesystem_safe():
    name = session_log_filename("2026-06-09_14-30-05")
    assert name.startswith("pioner_session_") and name.endswith(".log")
    for bad in (":", " ", "/"):
        assert bad not in name
    # The default timestamp format itself must not contain ':' (invalid on Windows).
    assert ":" not in SESSION_LOG_TIMESTAMP_FORMAT


def test_idempotent_no_duplicate_handlers(tmp_path):
    configure_logging(log_dir=str(tmp_path), timestamp="t1")
    assert len(_session_handlers()) == 1
    configure_logging(log_dir=str(tmp_path), timestamp="t2")
    assert len(_session_handlers()) == 1  # swapped, not stacked


def test_console_handler_optional(tmp_path):
    configure_logging(log_dir=str(tmp_path), timestamp="t3", console=True)
    # one FileHandler + one StreamHandler, both tagged
    kinds = sorted(type(h).__name__ for h in _session_handlers())
    assert kinds == ["FileHandler", "StreamHandler"]


def test_creates_missing_log_dir(tmp_path):
    target = tmp_path / "nested" / "logs"
    path = configure_logging(log_dir=str(target), timestamp="t4")
    assert path.parent == target and target.is_dir()
