"""Simple workspace test to verify setup."""

import pytest


def test_simple():
    """Simple test to verify pytest is working."""
    assert True


@pytest.mark.asyncio
async def test_simple_async():
    """Simple async test to verify async setup."""
    assert True