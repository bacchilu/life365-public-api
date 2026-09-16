"""Shared rules for customer integration request schemas."""

from pydantic import BaseModel, ConfigDict


class IntegrationRequestModel(BaseModel):
    """Reject unknown fields and hide input values in error text."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
