"""Regression checks for accidentally committed cloud keys and insecure defaults."""
from pathlib import Path

from scripts.check_tracked_secrets import scan_content


def test_cloud_tokens_are_detected_without_ever_echoing_the_secret():
    value = "sk-" + "A" * 35
    issues = scan_content("test_data.txt", "temporary = " + value)
    assert any("key" in label.lower() for _, label in issues)
    assert value not in repr(issues)


def test_example_credentials_must_be_blank():
    assert scan_content(".env.example", "OPENAI_API_KEY=") == []
    assert scan_content(".env.example", "DEEPSEEK_API_KEY=") == []
    assert scan_content(".env.example", "POSTGRES_PASSWORD=") == []
    assert scan_content(".env.example", "DATABASE_URL=") == []
    assert scan_content(".env.example", "POSTGRES_PASSWORD=some-real-secret")
    assert scan_content(".env.example", "DATABASE_URL=postgresql://user:secret@db/db")


def test_compose_default_password_is_blocked():
    unsafe = "$" + "{POSTGRES_PASSWORD:-old_default}"
    assert scan_content("docker-compose.yml", "POSTGRES_PASSWORD: " + unsafe)
    safe = "$" + "{POSTGRES_PASSWORD:?Set POSTGRES_PASSWORD in .env}"
    assert not scan_content("docker-compose.yml", "POSTGRES_PASSWORD: " + safe)


def test_settings_no_longer_hardcodes_database_user_password():
    source = (
        Path(__file__).resolve().parents[1]
        / "src" / "nomenclature_matcher" / "settings.py"
    ).read_text(encoding="utf-8")
    assert not scan_content("src/nomenclature_matcher/settings.py", source)
    env_example = (Path(__file__).resolve().parents[1] / ".env.example").read_text(
        encoding="utf-8"
    )
    assert not scan_content(".env.example", env_example)
