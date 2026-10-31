"""JSON API and PDF download endpoints."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, Response, abort, current_app, jsonify, send_file

from ..cv_data import CV_DATA

bp = Blueprint("api", __name__)


def _pdf_path() -> Path:
    return Path(current_app.config["CV_PDF_PATH"])


def _send_pdf(as_attachment: bool) -> Response:
    path = _pdf_path()
    if not path.is_file():
        abort(404, description="CV PDF file not found.")
    return send_file(
        path,
        mimetype="application/pdf",
        as_attachment=as_attachment,
        download_name="Alex_Maican_CV.pdf" if as_attachment else None,
        max_age=0,
    )


@bp.route("/api/cv")
def cv() -> Response:
    return jsonify(CV_DATA)


@bp.route("/download-pdf")
def download_pdf() -> Response:
    return _send_pdf(as_attachment=True)


@bp.route("/view-pdf")
def view_pdf() -> Response:
    return _send_pdf(as_attachment=False)
