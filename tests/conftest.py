import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    """A fresh app whose database and photos live in a temporary folder."""
    data_dir = tmp_path / "data"
    app = create_app(
        {
            "TESTING": True,
            "DATA_DIR": data_dir,
            "DATABASE": data_dir / "test.sqlite",
            "PHOTO_DIR": data_dir / "photos",
        }
    )
    yield app


@pytest.fixture
def client(app):
    return app.test_client()
