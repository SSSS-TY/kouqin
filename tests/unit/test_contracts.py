"""G-04…G-08：契约与配置回归（SPEC §3.2、§3.7）。

G-01/G-02/G-03 已由 `test_instrument_config.py` 与 `test_settings_config.py` 覆盖，此处不重复。
"""

from __future__ import annotations

import json
from pathlib import Path

from kouqin.core.compile import compile_plan
from kouqin.core.instrument import load_instrument
from kouqin.scores.kq import parse_kq
from kouqin.settings import load_settings

from tests.helpers import (
    EXPECTED_DIR,
    PINNED_MIDI,
    PINNED_PLAYBACK,
    score_text,
    shipped_instrument,
    shipped_settings,
    write_instrument,
    write_settings,
)


def test_g04_unknown_fields_are_tolerated(tmp_path: Path) -> None:
    path = write_settings(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["future_feature"] = {"enabled": True}
    data["playback"]["future_param"] = 123
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    settings = load_settings(path)
    assert settings.playback["min_hold_ms"] == PINNED_PLAYBACK["min_hold_ms"]


def test_g05_missing_fields_fall_back_to_defaults_with_warning(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"playback": {"min_hold_ms": 50}}, ensure_ascii=False), encoding="utf-8")

    settings = load_settings(path)
    assert settings.playback["min_hold_ms"] == 50
    assert "note_gap_ms" in settings.playback
    assert any(issue.level == "warning" for issue in settings.issues)


def test_g06_plan_json_schema(tmp_path: Path) -> None:
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path))
    plan = compile_plan(parse_kq(score_text("golden_bar.kq")), instrument, settings)
    data = plan.to_dict()

    for key in ("version", "title", "tempo_bpm", "speed", "transpose", "params", "notes", "events"):
        assert key in data
    ops = {event["op"] for event in data["events"]}
    assert ops <= {"key_down", "key_up", "mouse_down", "mouse_up"}
    times = [event["t_ms"] for event in data["events"]]
    assert times == sorted(times)
    assert all(t >= 0 for t in times)


def normalize(plan) -> dict:
    data = plan.to_dict()
    return {
        "tempo_bpm": data["tempo_bpm"],
        "speed": data["speed"],
        "transpose": data["transpose"],
        "offset_ms": data["offset_ms"],
        "params": data["params"],
        "notes": [
            {
                "start_ms": n["start_ms"],
                "duration_ms": n["duration_ms"],
                "pitch": n["pitch"],
                "repr": n["repr"],
                "key": n["fingering"]["key"],
                "buttons": n["fingering"]["buttons"],
            }
            for n in data["notes"]
        ],
        "events": data["events"],
    }


def test_g07_golden_plan_matches_hand_derived_expectation(tmp_path: Path) -> None:
    instrument = load_instrument(write_instrument(tmp_path, shipped_instrument()))
    settings = load_settings(write_settings(tmp_path))
    plan = compile_plan(parse_kq(score_text("golden_bar.kq")), instrument, settings)

    expected = json.loads((EXPECTED_DIR / "golden_bar.plan.json").read_text(encoding="utf-8"))
    expected.pop("_说明", None)
    assert normalize(plan) == expected


def test_g08_shipped_settings_match_pinned_test_values() -> None:
    """测试固定参数必须与仓库配置一致；若你调整了 config/settings.json，请同步更新 tests/helpers.py。"""
    shipped = shipped_settings()
    assert shipped["playback"] == PINNED_PLAYBACK
    assert shipped["midi"] == PINNED_MIDI

