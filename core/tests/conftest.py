from hscommon.testutil import app  # noqa

# The C extensions (core.pe._block, core.pe._cache) are built by
# `python build.py --modules`. Without them, most of this suite cannot
# even be collected -- and the bare ImportError that results says nothing
# about how to fix it. Fail here, loudly, with the fix, instead of
# letting the suite silently skip or crash on a cryptic import error.
try:
    import core.pe._block  # noqa: F401
    import core.pe._cache  # noqa: F401
except ImportError as e:
    raise ImportError(
        "DupeCleaner C extensions are not built. Run `python build.py --modules` "
        "from the repo root, then re-run pytest. (Original error: %s)" % e
    ) from e
