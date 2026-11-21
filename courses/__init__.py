"""The training application (prds/training-app-plan.md): courses served inside
the application behind the member's own sign-in, with each person's progress
and completion recorded. The course content lives in ``training/``; this
package serves it."""

from .router import router as api_router

__all__ = ["api_router"]
