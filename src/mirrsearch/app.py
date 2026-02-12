from flask import Flask

import internalLogic


def create_app():
    app = Flask(name)

    @app.route("/")
    def hello_world():
        return "<p>Hello, World!</p>"

    @app.route("/search")
    def search():
        return internalLogic("sample_database").search("example_query")

    return app


if name == 'main':
    app = create_app()
    app.run(port=8000, debug=True)
