"""Internal logic module for search operations with pagination"""
from mirrsearch.db import get_db


class InternalLogic:  # pylint: disable=too-few-public-methods
    """Internal logic for search operations with pagination"""

    def __init__(self, database, db_layer=None):
        self.database = database
        self.db_layer = db_layer if db_layer is not None else get_db()

    def search(self, query, docket_type_param=None, agency=None,
           cfr_part_param=None, start_date=None, end_date=None,
           page=1, page_size=10):
    # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
        """
        Search with pagination support.

        Args:
            query: Search query string
            docket_type_param: Filter by docket type
            agency: Filter by agency
            cfr_part_param: Filter by CFR part
            start_date: Filter results where modify_date >= start_date (YYYY-MM-DD)
            end_date: Filter results where modify_date <= end_date (YYYY-MM-DD)
            page: Page number (1-indexed)
            page_size: Number of results per page

        Returns:
            dict: Paginated response with metadata
        """
        all_results = self.db_layer.search(
            query,
            docket_type_param,
            agency,
            cfr_part_param,
            start_date=start_date,
            end_date=end_date
        )

        total_results = len(all_results)
        total_pages = (total_results + page_size - 1) // page_size

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        page_results = all_results[start_idx:end_idx]
        for result in page_results:
            cfr_refs = result.pop("cfr_refs", None)
            if cfr_refs is not None:
                result["cfrPart"] = [
                    {"title": ref.get("title"), "part": part, "link": link}
                    for ref in cfr_refs
                    for part, link in ref.get("cfrParts", {}).items()
                ]

        return {
            "results": page_results,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_results": total_results,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
        }
