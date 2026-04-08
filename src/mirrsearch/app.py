"""Flask application with pagination via HTTP headers"""
import os
from datetime import date, datetime
from flask import Flask, request, jsonify, send_from_directory, redirect, make_response
from mirrsearch.internal_logic import InternalLogic, _transform_cfr_refs
from mirrsearch.oauth_handler import OAuthHandler, OAuthCodeError, OAuthVerificationError
from mirrsearch.oauth_handler import TokenExpiredError, TokenInvalidError
from mirrsearch.db import get_db


def _get_search_params():
    """Extract and validate search parameters from the request."""
    cfr_parts_raw = [v for v in request.args.getlist('cfr_part') if v]
    cfr_parts_parsed = None

    if cfr_parts_raw:
        cfr_parts_parsed = []
        for cfr_str in cfr_parts_raw:
            if ':' not in cfr_str:
                continue
            title, part = cfr_str.split(':', 1)
            if not title or not part:
                continue
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


def _make_oauth_handler():
    """Create OAuthHandler from environment variables or AWS Secrets Manager."""
    use_aws = os.getenv("USE_AWS_SECRETS", "").lower() in {"1", "true", "yes", "on"}
    if use_aws:
        return _make_oauth_handler_from_aws()
    return OAuthHandler(
        base_url=os.getenv("BASE_URL", "http://localhost:80"),
        google_client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        google_client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        jwt_secret=os.getenv("JWT_SECRET", "dev-secret")
    )


def _make_oauth_handler_from_aws():
    """Create OAuthHandler from AWS Secrets Manager."""
    import boto3  # pylint: disable=import-outside-toplevel
    import json  # pylint: disable=import-outside-toplevel
    client = boto3.client(
        "secretsmanager",
        region_name=os.getenv("AWS_REGION", "us-east-1")
    )
    secret = json.loads(
        client.get_secret_value(
            SecretId=os.getenv("OAUTH_SECRET_NAME", "mirrulations/oauth")
        )["SecretString"]
    )
    return OAuthHandler(
        base_url=secret.get("base_url", ""),
        google_client_id=secret.get("google_client_id", ""),
        google_client_secret=secret.get("google_client_secret", ""),
        jwt_secret=secret.get("jwt_secret", "dev-secret")
    )


def _get_user_from_cookie(oauth_handler):
    """Extract and validate user info from JWT cookie. Returns dict or None."""
    token = request.cookies.get("jwt_token")
    if not token:
        return None
    try:
        user_id = oauth_handler.validate_jwt_token(token)
        name, email = user_id.split("|", 1)
        return {"name": name, "email": email}
    except (TokenExpiredError, TokenInvalidError, ValueError):
        return None


def _handle_oauth_callback(handler):
    """Exchange OAuth code for JWT cookie response. Returns response or None."""
    code = request.args.get("code")
    if not code:
        return None
    try:
        user_info = handler.exchange_code_for_user_info(code)
        user_id = f"{user_info['name']}|{user_info['email']}"
        token = handler.create_jwt_token(user_id)
        response = make_response(redirect("/"))
        response.set_cookie("jwt_token", token, httponly=True, samesite="Lax", path="/")
        return response
    except (OAuthCodeError, OAuthVerificationError):
        return redirect("/")


def create_app(dist_dir=None, db_layer=None, oauth_handler=None):  # pylint: disable=too-many-locals,too-many-statements
    """Create and configure Flask application"""
    if dist_dir is None:
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..')
        )
        dist_dir = os.path.join(project_root, 'frontend', 'dist')

    flask_app = Flask(__name__, static_folder=dist_dir, static_url_path='')
    flask_app.secret_key = os.getenv("JWT_SECRET", "dev-secret")

    @flask_app.route("/")
    def home():
        handler = oauth_handler or _make_oauth_handler()
        callback_response = _handle_oauth_callback(handler)
        if callback_response:
            return callback_response
        return send_from_directory(dist_dir, "index.html")

    @flask_app.route("/login")
    def login():
        handler = oauth_handler or _make_oauth_handler()
        authorization_url, _ = handler.get_authorization_url()
        return redirect(authorization_url)

    @flask_app.route("/logout")
    def logout():
        response = make_response(redirect("/"))
        response.delete_cookie("jwt_token")
        return response

    @flask_app.route("/auth/status")
    def auth_status():
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if user:
            return jsonify({"logged_in": True, "name": user["name"], "email": user["email"]})
        return jsonify({"logged_in": False})

    @flask_app.route("/search/")
    def search():
        handler = oauth_handler or _make_oauth_handler()
        if not _get_user_from_cookie(handler):
            return jsonify({"error": "Unauthorized"}), 401

        params = _get_search_params()
        page, page_size = _get_pagination_params()

        logic = InternalLogic("sample_database", db_layer=db_layer)
        result = logic.search(
            params['search_input'],
            params['docket_type'],
            params['agency'],
            params['cfr_part'],
            params['start_date'],
            params['end_date'],
            page=page,
            page_size=page_size
        )

        return _build_paginated_response(result['results'], result['pagination'])

    @flask_app.route("/agencies")
    def agencies():
        result = InternalLogic("sample_database", db_layer=db_layer).get_agencies()
        return jsonify(result)

    @flask_app.route("/collections", methods=["GET"])
    def get_collections():
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        result = db_layer.get_collections(user["email"])
        return jsonify(result)

    @flask_app.route("/collections", methods=["POST"])
    def create_collection():
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        name = (body.get("name") or "").strip()
        if not name:
            return jsonify({"error": "name is required"}), 400
        collection_id = db_layer.create_collection(user["email"], name)
        return jsonify({"collection_id": collection_id}), 201

    @flask_app.route("/collections/<int:collection_id>", methods=["DELETE"])
    def delete_collection(collection_id):
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        deleted = db_layer.delete_collection(collection_id, user["email"])
        if not deleted:
            return jsonify({"error": "Collection not found"}), 404
        return "", 204

    @flask_app.route("/collections/<int:collection_id>/dockets", methods=["GET"])
    def get_collection_dockets(collection_id):
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        page, page_size = _get_pagination_params()
        logic = InternalLogic("sample_database", db_layer=db_layer)
        result = logic.get_collection_dockets(
            collection_id, user["email"], page=page, page_size=page_size
        )
        if result is None:
            return jsonify({"error": "Collection not found"}), 404
        return _build_paginated_response(result['results'], result['pagination'])

    @flask_app.route("/collections/<int:collection_id>/dockets", methods=["POST"])
    def add_docket_to_collection(collection_id):
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        body = request.get_json(silent=True) or {}
        docket_id = (body.get("docket_id") or "").strip()
        if not docket_id:
            return jsonify({"error": "docket_id is required"}), 400
        added = db_layer.add_docket_to_collection(collection_id, docket_id, user["email"])
        if not added:
            return jsonify({"error": "Collection not found"}), 404
        return "", 204

    @flask_app.route("/collections/<int:collection_id>/dockets/<docket_id>", methods=["DELETE"])
    def remove_docket_from_collection(collection_id, docket_id):
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401
        removed = db_layer.remove_docket_from_collection(collection_id, docket_id, user["email"])
        if not removed:
            return jsonify({"error": "Collection not found"}), 404
        return "", 204

    @flask_app.route("/download/request", methods=["POST"])
    def request_download(): # pylint: disable=too-many-return-statements
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        body = request.get_json(silent=True) or {}
        docket_ids = body.get("docket_ids") or []
        data_format = (body.get("format") or "").strip().lower()
        include_binaries = bool(body.get("include_binaries", False))

        if not docket_ids:
            return jsonify({"error": "docket_ids is required"}), 400
        if len(docket_ids) > 10:
            return jsonify({"error": "Maximum of 10 dockets per download"}), 400
        if data_format not in ("raw", "csv"):
            return jsonify({"error": "format must be 'raw' or 'csv'"}), 400

        job_id = db_layer.create_download_job(
            user["email"], docket_ids, data_format, include_binaries
        )
        return jsonify({"job_id": job_id, "status": "started"}), 202

    @flask_app.route("/download/status/<job_id>", methods=["GET"])
    def download_status(job_id): # pylint: disable=too-many-return-statements
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        job = db_layer.get_download_job(job_id, user["email"])
        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify({
            "job_id": job_id,
            "status": job["status"],
            "format": job["format"],
            "docket_ids": job["docket_ids"],
            "created_at": job["created_at"],
            "completed_at": job.get("completed_at"),
            "up_to_date": job.get("up_to_date", True)
        })

    @flask_app.route("/download/<job_id>", methods=["GET"])
    def download_file(job_id): # pylint: disable=too-many-return-statements
        handler = oauth_handler or _make_oauth_handler()
        user = _get_user_from_cookie(handler)
        if not user:
            return jsonify({"error": "Unauthorized"}), 401

        job = db_layer.get_download_job(job_id, user["email"])
        if not job:
            return jsonify({"error": "Job not found"}), 404
        if job["status"] != "ready":
            return jsonify({"error": "Download not ready yet"}), 202

        s3_url = db_layer.get_download_s3_url(job_id, user["email"])
        if not s3_url:
            return jsonify({"error": "Download file not found"}), 404

        return redirect(s3_url)

    @flask_app.route("/dockets", methods=["GET"])
    def get_dockets_by_ids():
        handler = oauth_handler or _make_oauth_handler()
        if not _get_user_from_cookie(handler):
            return jsonify({"error": "Unauthorized"}), 401
        docket_ids = [v for v in request.args.getlist("docket_id") if v]
        if not docket_ids:
            return jsonify([])
        results = db_layer.get_dockets_by_ids(docket_ids)
        for result in results:
            if "modify_date" in result and isinstance(result["modify_date"], (date, datetime)):
                result["modify_date"] = result["modify_date"].isoformat()
            _transform_cfr_refs(result)
        return jsonify(results)

    return flask_app


app = create_app(db_layer=get_db())

if __name__ == '__main__':
    app.run(port=80, debug=True)
