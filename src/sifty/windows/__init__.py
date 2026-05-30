"""Windows-specific primitives (registry, winget, recycle bin, admin, …).

Everything that talks directly to the OS lives here so the ``core`` layer stays
about domain logic. Import these from core, never the reverse.
"""
