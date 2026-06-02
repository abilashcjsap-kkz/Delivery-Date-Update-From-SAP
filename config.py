"""Application configuration loaded from environment variables."""

import os


SAP_BASE_URL = os.getenv("SAP_BASE_URL", "").rstrip("/")
SAP_USERNAME = os.getenv("SAP_USERNAME", "")
SAP_PASSWORD = os.getenv("SAP_PASSWORD", "")
SAP_TIMEOUT_SECONDS = int(os.getenv("SAP_TIMEOUT_SECONDS", "30"))

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
GEMINI_URL = os.getenv(
    "GEMINI_URL",
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}",
)
