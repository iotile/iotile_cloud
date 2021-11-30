from .router_config import DB2, REDSHIFT_APPs


class StreamDataRouter(object):
    """
    A router to control all database operations on models in the
    Redshift applications.
    """

    def db_for_read(self, model, **hints):
        if model._meta.app_label in REDSHIFT_APPs:
            return DB2
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label in REDSHIFT_APPs:
            return DB2
        return None

    def allow_relation(self, obj1, obj2, **hints):
        if obj1._meta.app_label in REDSHIFT_APPs or obj2._meta.app_label in REDSHIFT_APPs:
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in REDSHIFT_APPs:
            return db == DB2
        return None
