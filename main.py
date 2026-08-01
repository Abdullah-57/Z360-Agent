# main.py — deployment entrypoint.
#
# FastAPI Cloud's launcher auto-discovers an app by looking for `main.py` (and
# then `app.py`) and running the first FastAPI instance it finds. Our actual
# application lives in server.py (with /health and /screen) and is UNCHANGED.
# This file simply re-exports that app under the conventional entrypoint name so
# the platform can find it without any extra configuration.
from server import app

__all__ = ["app"]
