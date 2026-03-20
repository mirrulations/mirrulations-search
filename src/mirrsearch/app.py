"""Flask application with pagination via HTTP headers"""
import os
from flask import Flask, request, jsonify, send_from_directory
from mirrsearch.internal_logic import InternalLogic


def _get_search_params():
    """Extract and validate search parameters from the request."""
    cfr_parts_raw = [v for v in request.args.getlist('cfr_part') if v]
    cfr_parts_parsed = None

    if cfr_parts_raw:
        cfr_parts_parsed = []
        for cfr_str in cfr_parts_raw:
            title, part = cfr_str.split(':', 1)
            cfr_parts_parsed.append({'title': title, 'part': part})

    return {
        'search_input': request.args.get('str') or 'example_query',
        'docket_type': request.args.get('docket_type'),
        'agency': [v for v in request.args.getlist('agency') if v] or None,
        'cfr_part': cfr_parts_parsed,
        'start_date': request.args.get('start_date') or None,
        'end_date': request.args.get('end_date') or None,
    }


def _get_pagination_params():
    """Extract and validate pagination parameters from the request."""
    page = max(request.args.get('page', default=1, type=int), 1)
    page_size = request.args.get('page_size', default=10, type=int)
    if page_size < 1 or page_size > 100:
        page_size = 10
    return page, page_size


def _build_paginated_response(results, pagination):
    """Build a JSON response with pagination metadata in HTTP headers."""
    response = jsonify(results)
    response.headers['X-Page'] = str(pagination['page'])
    response.headers['X-Page-Size'] = str(pagination['page_size'])
    response.headers['X-Total-Results'] = str(pagination['total_results'])
    response.headers['X-Total-Pages'] = str(pagination['total_pages'])
    response.headers['X-Has-Next'] = str(pagination['has_next']).lower()
    response.headers['X-Has-Prev'] = str(pagination['has_prev']).lower()
    return response


def create_app(dist_dir=None, db_layer=None):
    """Create and configure Flask application"""
    if dist_dir is None:
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..')
        )
        dist_dir = os.path.join(project_root, 'frontend', 'dist')

    flask_app = Flask(__name__, static_folder=dist_dir, static_url_path='')

    @flask_app.route("/")
    def home():
        return send_from_directory(dist_dir, "index.html")

    @flask_app.route("/search/")
    def search():
        params = _get_search_params()
        page, page_size = _get_pagination_params()

        logic = InternalLogic("sample_database", db_layer=db_layer)
        result = logic.search(
            params['search_input'],
            params['docket_type'],
            params['agency'],
            params['cfr_part'],
            start_date=params['start_date'],
            end_date=params['end_date'],
            page=page,
            page_size=page_size
        )

        return _build_paginated_response(result['results'], result['pagination'])

    return flask_app


app = create_app()

if __name__ == '__main__':
    app.run(port=80, debug=True)