"""Pytest configuration and shared fixtures."""

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture
def sample_comment_data() -> dict:
    """Sample comment data for testing."""
    return {
        "id": "abc123",
        "body": "Your form looks good, but watch your knee tracking.",
        "score": 15,
        "author": "experienced_lifter",
        "created_utc": "2024-01-15T12:00:00",
        "is_top_level": True,
    }


@pytest.fixture
def sample_post_data() -> dict:
    """Sample post data for testing."""
    return {
        "id": "xyz789",
        "lift_type": "Squat",
        "title": "Form check - 225lbs x 5 squat",
        "video_url": "https://v.redd.it/example/DASH_720.mp4",
        "created_utc": "2024-01-15T10:00:00",
        "author": "gym_rat_42",
        "post_score": 25,
    }
