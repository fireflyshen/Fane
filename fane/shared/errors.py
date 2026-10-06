class FaneError(Exception):
    pass


class ConfigError(FaneError):
    pass


class ProviderError(FaneError):
    pass


class SyncError(FaneError):
    pass


class TemplateError(FaneError):
    pass
