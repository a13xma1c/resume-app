"""Flask blueprints for the resume website."""

from .api import bp as api_bp
from .contact import bp as contact_bp
from .pages import bp as pages_bp

__all__ = ["api_bp", "contact_bp", "pages_bp"]
