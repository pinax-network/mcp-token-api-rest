"""
Pytest configuration and fixtures
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv


def pytest_configure(config):
    """
    Load environment variables from .env before running tests
    """
    # Load .env file from project root
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=True)
        print(f"\n✓ Loaded environment from {env_path}")
    else:
        print(f"\n⚠ No .env file found at {env_path}")


@pytest.fixture(scope="session")
def verify_env_loaded():
    """Verify that environment variables are loaded"""
    api_token = os.getenv("API_TOKEN")
    if api_token:
        print(f"\n✓ API_TOKEN loaded: {api_token[:10]}...")
    else:
        print("\n⚠ API_TOKEN not found in environment")
    return api_token is not None
