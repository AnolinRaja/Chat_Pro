import pytest

from app.services.rate_limiter import auth_rate_limiter


@pytest.fixture(autouse=True)
def reset_auth_rate_limiter():
    auth_rate_limiter.clear()
    yield
    auth_rate_limiter.clear()