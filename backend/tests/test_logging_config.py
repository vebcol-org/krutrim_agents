from __future__ import annotations

from krutrim_agent_management import logging_config
from krutrim_agent_management.config import settings


def test_configure_logging_creates_component_dir_and_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    monkeypatch.setattr(settings, "log_rotation", "1 day")
    monkeypatch.setattr(settings, "log_retention", "3 days")
    monkeypatch.setattr(logging_config, "_configured", set())

    logging_config.configure_logging("worker")
    logging_config.configure_logging("worker")  # second call is a no-op

    worker_dir = tmp_path / "logs" / "worker"
    assert worker_dir.is_dir()
    assert logging_config._configured == {"worker"}


def test_configure_logging_separates_server_and_worker_sinks(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "log_dir", tmp_path / "logs")
    monkeypatch.setattr(logging_config, "_configured", set())

    logging_config.configure_logging("server")
    logging_config.configure_logging("worker")

    assert (tmp_path / "logs" / "server").is_dir()
    assert (tmp_path / "logs" / "worker").is_dir()
    assert logging_config._configured == {"server", "worker"}
