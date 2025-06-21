# src/api/__init__.py
"""
Production API layer for Row Match Recognize.

This package provides RESTful API endpoints and service interfaces for
production deployment of the row pattern matching system.
"""

from .service import MatchRecognizeService
from .endpoints import create_app, HealthAPI, QueryAPI
from .middleware import SecurityMiddleware, LoggingMiddleware, MetricsMiddleware

__all__ = [
    'MatchRecognizeService',
    'create_app',
    'HealthAPI',
    'QueryAPI',
    'SecurityMiddleware',
    'LoggingMiddleware',
    'MetricsMiddleware'
]
