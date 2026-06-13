class FaneError(Exception):
    pass


class ConfigError(FaneError):
    pass


class ProviderError(FaneError):
    pass
