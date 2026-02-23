from mirrsearch.db import get_db


class InternalLogic:  # pylint: disable=too-few-public-methods
    def __init__(self, database, db_layer=None):
        self.database = database
        self.db_layer = db_layer if db_layer is not None else get_db()

    def search(self, query, filter_param=None):
        search_results = self.db_layer.search(query, filter_param)
        return search_results
        