from pathlib import Path
from flask import Flask, jsonify, render_template, send_file, abort
from .cv_data import CV_DATA

BASE_DIR = Path(__file__).resolve().parent.parent.parent
PDF_PATH = BASE_DIR / "Alex Maican - CV.pdf"


def create_app() -> Flask:
    """Create and configure the Flask CV application."""
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )

    @app.route("/")
    def index():
        return render_template("index.html", cv=CV_DATA)

    @app.route("/api/cv")
    def api_cv():
        return jsonify(CV_DATA)

    @app.route("/download-pdf")
    def download_pdf():
        if PDF_PATH.exists():
            return send_file(
                PDF_PATH,
                mimetype="application/pdf",
                as_attachment=True,
                download_name="Alex_Maican_CV.pdf",
            )
        abort(404, description="CV PDF file not found.")

    @app.route("/view-pdf")
    def view_pdf():
        if PDF_PATH.exists():
            return send_file(
                PDF_PATH,
                mimetype="application/pdf",
                as_attachment=False,
            )
        abort(404, description="CV PDF file not found.")

    return app


def main():
    """Entry point for CLI runner."""
    app = create_app()
    app.run(host="0.0.0.0", port=5123, debug=True)


if __name__ == "__main__":
    main()
