"""Compatibility adapter for the historical sync service constructor."""
from fane.application.sync import SyncService as ApplicationSyncService, SyncReport, SourceReport
from fane.bootstrap import build_converter


class SyncService(ApplicationSyncService):
    def __init__(self, config, job_name, job):
        super().__init__(config, job_name, job, converter=build_converter(config))
