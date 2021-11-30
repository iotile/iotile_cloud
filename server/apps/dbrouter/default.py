from .router_config import DB1, DB2, DB3, REDSHIFT_APPs, STREAM_TIME_SERIES_APPs

NOT_DEFAULT_APPS = REDSHIFT_APPs + STREAM_TIME_SERIES_APPs


class DefaultRouter(object):
    def db_for_read(self, model, **hints):
        if model._meta.app_label not in NOT_DEFAULT_APPS:
            return DB1
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label not in NOT_DEFAULT_APPS:
            return DB1
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label not in NOT_DEFAULT_APPS and obj2._meta.app_label not in NOT_DEFAULT_APPS:
            return True
        return False

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label not in NOT_DEFAULT_APPS:
            # return db != DB2 and db != DB3
            return db != DB2
        return None
