def test_all_public_imports():
    """Verify all public API symbols are importable from the top-level package."""
    from zeno import Zeno
    from zeno import Collection
    from zeno import Auth
    from zeno import ZenoError
    from zeno import TextField, IntField, FloatField, BoolField
    from zeno import DateTimeField, URLField, JSONField, RelationField

    assert Zeno is not None
    assert Collection is not None
    assert Auth is not None
    assert ZenoError is not None


def test_dotenv_loading(tmp_path, monkeypatch):
    """Verify .env files are loaded."""
    import os
    env_file = tmp_path / ".env"
    env_file.write_text("ZENO_TEST_VAR=hello_from_dotenv\n")
    monkeypatch.chdir(tmp_path)

    from dotenv import load_dotenv
    load_dotenv(str(env_file))

    assert os.getenv("ZENO_TEST_VAR") == "hello_from_dotenv"
