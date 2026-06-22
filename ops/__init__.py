"""Staff operations console for the durable submission store — V2 Phase 2.

A read + re-drive view over the captured submissions (`/ops`), gated by the same
EspoCRM team-based auth as the assignment dashboard (``assignments.auth``). Staff
see every submission's status, age, attempts, and last error, and can re-drive a
stuck or held one so the worker re-runs it (resumably, no duplicates).
"""

from .router import router as api_router

__all__ = ["api_router"]
