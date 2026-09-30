"""Project Fortuna — lottery randomness and forecasting research infrastructure.

Phase 0: repository initialization, rule provenance, and statistical-regime
verification. No predictive modeling is performed in this phase.
"""

import os as _os

# A stray SSLKEYLOGFILE pointing at an unwritable path breaks urllib3's SSL
# context creation at import time (inside `requests`). It is a debugging
# variable that must not be inherited by reproducible research processes.
_os.environ.pop("SSLKEYLOGFILE", None)

__version__ = "0.1.0"
