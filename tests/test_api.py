"""Tests for the JSON API and PDF endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient

from resumeapp import create_app
from resumeapp.cv_data import CV_DATA

from .helpers import RecordingMailer


def test_api_cv_returns_full_structured_data(client: FlaskClient) -> None:
    response = client.get("/api/cv")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/json"
    data = response.get_json()
    assert data == CV_DATA


def test_api_cv_shape(client: FlaskClient) -> None:
    data = client.get("/api/cv").get_json()
    assert data["personal"]["name"] == "Alex Maican"
    assert data["personal"]["title"] == "Big Data Engineer"
    assert len(data["experience"]) == 4
    assert len(data["education"]) == 3
    assert len(data["certifications"]) == 4
    assert "Data Engineering & Distributed Systems" in data["skills"]


def test_api_cv_rejects_post(client: FlaskClient) -> None:
    assert client.post("/api/cv").status_code == 405


def test_download_pdf_as_attachment(client: FlaskClient, pdf_file: Path) -> None:
    response = client.get("/download-pdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    disposition = response.headers["Content-Disposition"]
    assert disposition.startswith("attachment")
    assert "Alex_Maican_CV.pdf" in disposition
    assert response.data == pdf_file.read_bytes()
    response.close()


def test_view_pdf_inline(client: FlaskClient, pdf_file: Path) -> None:
    response = client.get("/view-pdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Content-Disposition"].startswith("inline")
    assert response.data.startswith(b"%PDF")
    response.close()


def test_pdf_endpoints_404_when_file_missing(
    app_config: dict[str, Any], mailer: RecordingMailer, tmp_path: Path
) -> None:
    app_config["CV_PDF_PATH"] = str(tmp_path / "missing.pdf")
    client = create_app(app_config, mailer=mailer).test_client()
    for path in ("/download-pdf", "/view-pdf"):
        response = client.get(path)
        assert response.status_code == 404
        assert "CV PDF file not found." in response.get_data(as_text=True)


def test_pdf_endpoint_404_when_path_is_a_directory(
    app_config: dict[str, Any], mailer: RecordingMailer, tmp_path: Path
) -> None:
    app_config["CV_PDF_PATH"] = str(tmp_path)
    client = create_app(app_config, mailer=mailer).test_client()
    assert client.get("/download-pdf").status_code == 404


def test_pdf_path_is_configurable_via_env(
    monkeypatch: pytest.MonkeyPatch, pdf_file: Path, mailer: RecordingMailer
) -> None:
    monkeypatch.setenv("CV_PDF_PATH", str(pdf_file))
    app = create_app({"TESTING": True}, mailer=mailer)
    assert app.config["CV_PDF_PATH"] == str(pdf_file)
    response = app.test_client().get("/view-pdf")
    assert response.status_code == 200
    response.close()
