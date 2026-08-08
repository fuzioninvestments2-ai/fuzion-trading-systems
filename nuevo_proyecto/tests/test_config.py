from nuevo_proyecto.config import Config


def test_defaults_cuando_no_hay_entorno(monkeypatch):
    for var in ("APP_NAME", "ENVIRONMENT", "LOG_LEVEL", "DEBUG"):
        monkeypatch.delenv(var, raising=False)

    config = Config.from_env(load_dotenv_file=False)

    assert config.app_name == "nuevo_proyecto"
    assert config.environment == "dev"
    assert config.log_level == "INFO"
    assert config.debug is False


def test_lee_valores_del_entorno(monkeypatch):
    monkeypatch.setenv("APP_NAME", "mi_app")
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("DEBUG", "true")

    config = Config.from_env(load_dotenv_file=False)

    assert config.app_name == "mi_app"
    assert config.environment == "prod"
    assert config.log_level == "DEBUG"
    assert config.debug is True


def test_debug_acepta_valores_no_booleanos(monkeypatch):
    monkeypatch.setenv("DEBUG", "no")

    assert Config.from_env(load_dotenv_file=False).debug is False
