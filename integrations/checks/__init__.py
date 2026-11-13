"""One module per integration test (integrations/testing.py). Each exposes
``async def run(settings, deps=None) -> dict`` and a ``Deps`` dataclass whose
defaults are the real clients, so tests pass fakes."""
