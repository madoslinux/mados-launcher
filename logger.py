"""Logger for madOS Launcher."""

import sys
from datetime import datetime


class Logger:
    def __init__(self, name="mados-launcher"):
        self.name = name

    def info(self, msg):
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [INFO] {msg}",
            file=sys.stderr,
            flush=True,
        )

    def debug(self, msg):
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [DEBUG] {msg}",
            file=sys.stderr,
            flush=True,
        )

    def error(self, msg):
        print(
            f"[{datetime.now().strftime('%H:%M:%S')}] [ERROR] {msg}",
            file=sys.stderr,
            flush=True,
        )


log = Logger()
