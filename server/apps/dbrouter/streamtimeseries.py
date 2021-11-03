from .router_config import STREAM_TIME_SERIES_APPs, DB3


class StreamTimeSeriesRouter:
    """
    A router to control all database operations on StreamTimeSeries models.
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label in STREAM_TIME_SERIES_APPs:
            return DB3
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in STREAM_TIME_SERIES_APPs:
            return DB3
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in STREAM_TIME_SERIES_APPs or obj2._meta.app_label in STREAM_TIME_SERIES_APPs:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in STREAM_TIME_SERIES_APPs:
            return db == DB3
        return None
