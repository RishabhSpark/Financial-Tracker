import os
import shutil
import tempfile
import yaml
import pytest
from app.core.logger import setup_logger
import io
import logging

@pytest.fixture
def temp_yaml_config():
    temp_dir = tempfile.mkdtemp()
    log_dir = os.path.join(temp_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)

    config = {
        "logger": {
            "name": "test_logger",
            "level": "DEBUG",
            "log_dir": log_dir,
            "file_name": "test.log",
            "format": {
                "pattern": "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S"
            },
            "handlers": {
                "console": {
                    "enabled": True,
                    "level": "WARNING"
                },
                "file": {
                    "enabled": True,
                    "level": "DEBUG"
                }
            }
        }
    }

    config_path = os.path.join(temp_dir, "logger_config.yaml")
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    yield config_path, log_dir

    shutil.rmtree(temp_dir)


def test_logger_logs_to_file(temp_yaml_config):
    config_path, log_dir = temp_yaml_config
    logger = setup_logger(config_path)
    logger.debug("Debug log to file")
    logger.error("Error log to file")

    log_path = os.path.join(log_dir, "test.log")
    assert os.path.exists(log_path)

    with open(log_path, "r") as f:
        content = f.read()
    assert "Debug log to file" in content
    assert "Error log to file" in content


def test_console_handler_filters_logs(temp_yaml_config):
    config_path, _ = temp_yaml_config
    logger = setup_logger(config_path)

    stream = io.StringIO()
    # Create a console handler with a stream we control
    console_handler = logging.StreamHandler(stream)
    console_handler.setLevel(logging.WARNING)
    formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(formatter)

    # Clear existing handlers and add our controlled console handler
    logger.handlers.clear()
    logger.addHandler(console_handler)
    logger.propagate = False

    logger.debug("debug should NOT be in console")
    logger.warning("warning SHOULD be in console")

    stream.seek(0)
    output = stream.read()

    assert "warning SHOULD be in console" in output
    assert "debug should NOT be in console" not in output


def test_logger_missing_logger_section(tmp_path):
    # malformed YAML
    broken_config = {"not_logger": {}}
    path = tmp_path / "bad.yaml"
    with open(path, "w") as f:
        yaml.dump(broken_config, f)

    with pytest.raises(ValueError, match="Logger config section 'logger' not found"):
        setup_logger(str(path))
