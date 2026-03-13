"""Tests for BiomechanicalFeatures Pydantic model."""

import json

import pytest
from pydantic import ValidationError

from autocoach.pose.models import BiomechanicalFeatures

pytestmark = pytest.mark.unit


def _make_features(**overrides: object) -> BiomechanicalFeatures:
    defaults: dict[str, object] = {
        "video_id": "abc",
        "lift_type": "Squat",
        "knee_angles": [160.0, 90.0, 155.0],
        "hip_angles": [170.0, 85.0, 165.0],
        "back_angles": [5.0, 40.0, 8.0],
        "min_knee_angle": 90.0,
        "min_hip_angle": 85.0,
        "max_back_angle": 40.0,
        "phase_labels": ["descent", "bottom", "ascent"],
        "view_confidence": 0.9,
        "dominant_side": "left",
    }
    return BiomechanicalFeatures(**{**defaults, **overrides})


class TestBiomechanicalFeatures:
    def test_model_dump_json_is_valid_json(self) -> None:
        json.loads(_make_features().model_dump_json())

    def test_frozen_prevents_mutation(self) -> None:
        f = _make_features()
        with pytest.raises(ValidationError):
            f.min_knee_angle = 0.0  # type: ignore[misc]

    def test_model_dump_contains_required_keys(self) -> None:
        d = _make_features().model_dump()
        assert {
            "video_id",
            "lift_type",
            "knee_angles",
            "hip_angles",
            "back_angles",
            "min_knee_angle",
            "min_hip_angle",
            "max_back_angle",
            "phase_labels",
            "view_confidence",
            "dominant_side",
        }.issubset(d.keys())
