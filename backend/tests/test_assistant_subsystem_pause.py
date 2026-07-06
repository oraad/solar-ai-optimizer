"""Assistant deterministic subsystem pause/resume parsing."""

from __future__ import annotations

from app.llm.assistant import Assistant
from app.config import Settings


def _assistant() -> Assistant:
    return Assistant(Settings())


def test_parse_pause_shedding():
    ov = _assistant().parse_intent("please pause shedding now")
    assert ov is not None
    assert ov.pause_shedding is True
    assert ov.pause_engine is None


def test_parse_pause_grid_charge():
    ov = _assistant().parse_intent("pause grid charge")
    assert ov is not None
    assert ov.pause_grid_charge is True
    assert ov.pause_engine is None


def test_parse_pause_optimization():
    ov = _assistant().parse_intent("pause optimization")
    assert ov is not None
    assert ov.pause_optimization is True


def test_parse_pause_all():
    ov = _assistant().parse_intent("pause")
    assert ov is not None
    assert ov.pause_engine is True


def test_parse_resume_grid():
    ov = _assistant().parse_intent("resume grid")
    assert ov is not None
    assert ov.pause_grid_charge is False


def test_parse_force_grid_charge_pauses():
    ov = _assistant().parse_intent("force grid charge")
    assert ov is not None
    assert ov.force_grid_charge is True
    assert ov.pause_grid_charge is True
