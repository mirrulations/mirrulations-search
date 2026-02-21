from mirrsearch.db import get_db


class InternalLogic:  # pylint: disable=too-few-public-methods
    def __init__(self, database):
        self.database = database

    def search(self, query, filter_param=None):
        db_layer = get_db()
        search_results = db_layer.search(query, filter_param)
        return search_results
