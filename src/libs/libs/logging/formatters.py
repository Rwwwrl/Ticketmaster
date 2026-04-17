import json
import logging
from datetime import datetime, timezone

from libs.common.enums import ServiceNameEnum
from libs.context_vars import request_id_var
from libs.logging.enums import ProcessTypeEnum

_APP_NAME = "ticketmaster"


class AWSJsonFormatter(logging.Formatter):
    _STANDARD_ATTRS: frozenset[str] = frozenset(
        {
            "name",
            "msg",
            "args",
            "created",
            "relativeCreated",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "pathname",
            "filename",
            "module",
            "levelno",
            "levelname",
            "thread",
            "threadName",
            "process",
            "processName",
            "msecs",
            "message",
            "taskName",
        }
    )

    def __init__(self, service_name: ServiceNameEnum, process_type: ProcessTypeEnum) -> None:
        super().__init__()
        self._service_name = service_name
        self._process_type = process_type

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "severity": record.levelname,
            "message": record.getMessage(),
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "app": _APP_NAME,
            "service": self._service_name.value,
            "process_type": self._process_type.value,
            "request_id": request_id_var.get(),
            "logger": record.name,
            "source_location": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }

        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key not in self._STANDARD_ATTRS and key not in log_entry:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


class DevFormatter(logging.Formatter):
    def __init__(self, service_name: ServiceNameEnum, process_type: ProcessTypeEnum) -> None:
        identity = f"{_APP_NAME} | {service_name.value}/{process_type.value}"
        fmt = f"%(asctime)s | %(levelname)-8s | {identity} | %(request_id)s | %(name)s | %(message)s"
        super().__init__(fmt=fmt, datefmt="%H:%M:%S")

    def format(self, record: logging.LogRecord) -> str:
        record.request_id = request_id_var.get()
        return super().format(record=record)
