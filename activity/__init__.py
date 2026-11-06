"""The activity page — every change by one person or in a date range, across
every record (mentor login integrity plan § 4.5, step 6)."""

from .router import router as api_router

__all__ = ["api_router"]
