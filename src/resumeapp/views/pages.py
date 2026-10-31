"""Content pages: home, experience, skills, education and the full CV."""

from __future__ import annotations

from flask import Blueprint, render_template

from ..cv_data import CV_DATA

bp = Blueprint("pages", __name__)


def _stats() -> dict[str, int]:
    """Small numbers shown on the home page cards."""
    return {
        "roles": len(CV_DATA["experience"]),
        "skills": sum(len(items) for items in CV_DATA["skills"].values()),
        "skill_categories": len(CV_DATA["skills"]),
        "degrees": len(CV_DATA["education"]),
        "certifications": len(CV_DATA["certifications"]),
        "languages": len(CV_DATA["languages"]),
    }


@bp.route("/")
def home() -> str:
    current_role = next((exp for exp in CV_DATA["experience"] if exp.get("is_current")), None)
    return render_template("home.html", stats=_stats(), current_role=current_role)


@bp.route("/experience")
def experience() -> str:
    # Every distinct technology across roles, for the filter "quick picks".
    seen: dict[str, None] = {}
    for exp in CV_DATA["experience"]:
        for tech in exp.get("key_technologies", []):
            seen.setdefault(tech, None)
    return render_template("experience.html", technologies=list(seen))


@bp.route("/skills")
def skills() -> str:
    return render_template("skills.html")


@bp.route("/education")
def education() -> str:
    return render_template("education.html")


@bp.route("/cv")
def full_cv() -> str:
    return render_template("cv.html")
