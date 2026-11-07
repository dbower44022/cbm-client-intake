"""The chapter website's side of the chapter applications.

What the Association's chapter connector reads: the Website group of System
Settings, the logo and header graphic, and (piece B) the key pages. Plan:
``prds/chapter-website-plan.md``. Every address is public and unauthenticated
by design, and answers 404 while ``WEBSITE_API`` is off.
"""

from .router import public_router

__all__ = ["public_router"]
