import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_rejects_non_postgres_database_url_without_printing_credentials():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url="sqlite:///must-not-leak.db")
    assert "must-not-leak" not in str(error.value)


@pytest.mark.parametrize("timeout", [0, -1, 11])
def test_rejects_invalid_database_timeout(timeout):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://unit:unit@localhost:1/unit",
            database_timeout_seconds=timeout,
        )
