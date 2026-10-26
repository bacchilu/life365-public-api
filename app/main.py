from fastapi import FastAPI

from app.api.application import create_api_application
from app.api.sandbox import create_sandbox_application

app: FastAPI = create_api_application("Life365 Public API")
app.mount("/sandbox", create_sandbox_application(), name="sandbox")
