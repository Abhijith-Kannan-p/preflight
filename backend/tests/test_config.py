import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://u:p@ep-x.neon.tech/db?sslmode=require",
            "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require",
        ),
        ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
        ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ],
)
def test_plain_postgres_urls_use_psycopg(given: str, expected: str) -> None:
    assert Settings(database_url=given).database_url == expected


def test_cors_origins_are_split() -> None:
    settings = Settings(cors_origins="https://a.vercel.app, https://b.example ,")
    assert settings.cors_origin_list == ["https://a.vercel.app", "https://b.example"]
