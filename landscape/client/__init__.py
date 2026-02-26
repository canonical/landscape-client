__all__ = [
    "IS_CORE",
    "IS_SNAP",
    "USER",
    "GROUP",
    "UA_DATA_DIR",
    "DEFAULT_CONFIG",
]

_DEPRECATION_MSG = (
    "Direct import from 'landscape.client' is deprecated "
    "and will be removed in landscape-client 28.0X. "
    "Import from 'landscape.client.environment' instead."
)


def __getattr__(name):  # pragma: no cover
    if name in __all__:
        import warnings

        import landscape.client.environment as env

        warnings.warn(_DEPRECATION_MSG, DeprecationWarning, stacklevel=2)
        return getattr(env, name)

    raise AttributeError(f"module 'landscape.client' has no attribute '{name}'")


def __dir__():  # pragma: no cover
    return __all__
