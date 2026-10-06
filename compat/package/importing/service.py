"""Compatibility adapter for the historical sync service constructor."""
from fane.bill.build import build_converter
from fane.bill.sync import SourceReport as SourceReport
from fane.bill.sync import SyncReport as SyncReport
from fane.bill.sync import SyncService as ApplicationSyncService


class SyncService(ApplicationSyncService):
    def __init__(self, config, job_name, job):
        super().__init__(config, job_name, job, converter=build_converter(config))

