"""Global test fixtures for HA Messenger.

Uses ``pytest-homeassistant-custom-component`` to provide the ``hass``
fixture, ``MockConfigEntry``, and the ``enable_custom_integrations`` hook
that lets HA discover our integration under ``custom_components/``.
"""
from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make ``custom_components/ha_messenger`` importable in every test."""
    yield
