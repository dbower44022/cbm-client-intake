"""Workspace Directories — CRM-style browsable grids (companies / contacts /
mentors) launched from the portal. One engine, one router per kind."""

from __future__ import annotations

from .config import DIRECTORIES, DirectoryConfig
from .router import make_router

__all__ = ["DIRECTORIES", "DirectoryConfig", "make_router"]
