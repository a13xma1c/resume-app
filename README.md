# Alex Maican - Interactive CV Web App

A modern, responsive CV & Portfolio web application built with **Python**, **Flask**, and managed with **uv**. The content is modeled directly on Alex Maican's CV (`Alex Maican - CV.pdf`).

## Features

- **Full CV Profile & Experience**: Complete breakdown of work history (IBM, eMAG, Orange Services, alfrednet), education, certifications, and technical skills.
- **Interactive UI**:
  - **Dark / Light Mode**: Theme toggle with automatic system preference detection and `localStorage` persistence.
  - **Live Filter / Search**: Filter work experience dynamically by keywords, technologies (e.g. Spark, Airflow, GCP), or company names.
  - **Quick Copy**: Click-to-copy buttons for email and phone numbers with toast notifications.
  - **Interactive Tech Tags**: Click any skill badge or tech tag to immediately filter matching roles.
- **PDF Download & View**: Direct download (`/download-pdf`) and inline viewing of the source CV PDF.
- **REST API**: Accessible `/api/cv` JSON endpoint providing full structured resume data.
- **Print Optimization**: Tailored `@media print` stylesheet for clean physical prints or browser PDF exports.

---

## Quickstart with `uv`

### 1. Install dependencies
```bash
uv sync
```

### 2. Run the application
You can run the application using `uv`:

```bash
uv run python app.py
```
or via the installed package script:
```bash
uv run resumeapp
```
or with Flask CLI:
```bash
uv run flask --app app run --port 5000
```

Open [http://localhost:5000](http://localhost:5000) in your web browser.

---

## Endpoints

| Route | Description |
|---|---|
| `/` | Interactive CV web interface |
| `/api/cv` | Structured CV data in JSON format |
| `/download-pdf` | Download original `Alex Maican - CV.pdf` |
| `/view-pdf` | View PDF inline in the browser |

---

## Testing

Run the test suite with `pytest`:

```bash
uv run pytest
```
