import pytest

from terrasignal.synth.generator import Portfolio, generate


@pytest.fixture(scope="session")
def portfolio() -> Portfolio:
    """One small, seeded portfolio shared by the test session."""
    return generate(seed=7, n_properties=40, n_tenants=160)
