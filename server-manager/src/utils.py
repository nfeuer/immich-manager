"""
Shared utilities for the Immich Server Manager.
"""

import os

# Subprocess environment with NOTIFY_SOCKET stripped so child processes don't
# accidentally send sd_notify messages intended for this process.
CLEAN_ENV = {k: v for k, v in os.environ.items() if k != "NOTIFY_SOCKET"}
