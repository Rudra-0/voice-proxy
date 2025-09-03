# Expose the FastAPI app at the package level
from .main import app

__all__ = ["app"]
