# Core

## logger
### Usage
```
from app.core.logger import setup_logger

logger = setup_logger('logger_config.yaml')
logger.info("This is an info log message")
logger.error("This is an error log message")
```

- Uses `logging` from the Python standard library.
- Logger structure and saved can be stored in yaml. Defaults to `app/config/logger_config.yaml`
- File logs are saved in the `logs/` directory:
