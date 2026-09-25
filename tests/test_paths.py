from pathlib import Path

from app.paths import default_state_dir


def test_default_state_dir_uses_source_checkout_data_dir(tmp_path):
    root = tmp_path / "repo"
    package_dir = root / "app"
    package_dir.mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='example'\n")

    assert default_state_dir(package_dir, environ={}, home=tmp_path / "home") == root / ".data"


def test_default_state_dir_honors_explicit_override(tmp_path):
    package_dir = tmp_path / "site-packages" / "app"
    package_dir.mkdir(parents=True)

    result = default_state_dir(
        package_dir,
        environ={"STELLAR_EXPORTER_STATE_DIR": str(tmp_path / "state")},
        home=tmp_path / "home",
    )

    assert result == tmp_path / "state"


def test_default_state_dir_uses_xdg_for_installed_package(tmp_path):
    package_dir = tmp_path / "site-packages" / "app"
    package_dir.mkdir(parents=True)

    result = default_state_dir(
        package_dir,
        environ={"XDG_STATE_HOME": str(tmp_path / "xdg-state")},
        home=tmp_path / "home",
    )

    assert result == tmp_path / "xdg-state" / "stellar-data-exporter"


def test_default_state_dir_falls_back_to_user_state_dir(tmp_path):
    package_dir = tmp_path / "site-packages" / "app"
    package_dir.mkdir(parents=True)
    home = tmp_path / "home"

    assert default_state_dir(package_dir, environ={}, home=home) == (
        home / ".local" / "state" / "stellar-data-exporter"
    )
