import pytest

from app.queue.service import BACKOFF_BASE_SECONDS, BACKOFF_MAX_SECONDS, backoff_seconds


@pytest.mark.parametrize("attempt", [1, 2, 3, 4])
def test_backoff_grows_exponentially_within_jitter_bounds(attempt: int) -> None:
    delay = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
    for _ in range(50):
        assert delay / 2 <= backoff_seconds(attempt) <= delay


def test_backoff_is_capped() -> None:
    for _ in range(50):
        assert backoff_seconds(50) <= BACKOFF_MAX_SECONDS
