import pytest
from resumeapp.app import create_app
from resumeapp.cv_data import CV_DATA


@pytest.fixture
def client():
    app = create_app()
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_index_page(client):
    response = client.get("/")
    assert response.status_code == 200
    html = response.data.decode("utf-8")
    assert "Alex Maican" in html
    assert "Big Data Engineer" in html
    assert "alexmcn07@gmail.com" in html
    assert "+40741696017" in html
    assert "Apache Spark" in html
    assert "IBM" in html
    assert "eMAG" in html
    assert "Orange Services" in html
    assert "Databricks Certified Data Engineer Associate" in html


def test_api_cv_endpoint(client):
    response = client.get("/api/cv")
    assert response.status_code == 200
    data = response.get_json()
    assert data["personal"]["name"] == "Alex Maican"
    assert data["personal"]["title"] == "Big Data Engineer"
    assert len(data["experience"]) == 4
    assert len(data["education"]) == 3
    assert len(data["certifications"]) == 4
    assert "Data Engineering & Distributed Systems" in data["skills"]


def test_download_pdf(client):
    response = client.get("/download-pdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]
    assert "Alex_Maican_CV.pdf" in response.headers["Content-Disposition"]


def test_view_pdf(client):
    response = client.get("/view-pdf")
    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/pdf"
