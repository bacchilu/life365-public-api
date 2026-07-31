from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.api.dependencies import get_current_user
from app.application.domain import AuthenticatedUser
from app.application.dtos import ProductRecommendation

from . import composition

router: APIRouter = APIRouter(tags=["products"])


class ProductRecommendationResponse(BaseModel):
    code: str | None
    name: str
    image_url: str | None
    description: str
    product_url: str


@router.get(
    "/products/recommend",
    summary="Recommend products",
    response_model=list[ProductRecommendationResponse],
)
async def recommend_products(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    order_id: Annotated[int | None, Query()] = None,
    customer_id: Annotated[int | None, Query()] = None,
) -> list[ProductRecommendationResponse]:
    """
    Return product recommendations for an authenticated request context.

    Provide exactly one positive identifier:

    - `order_id` uses the products in an existing order as the recommendation
      context.
    - `customer_id` uses the customer's purchase history as the recommendation
      context.

    Providing both identifiers or neither identifier returns `400 Bad Request`.
    """
    if (order_id is None) == (customer_id is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide exactly one of order_id or customer_id",
        )

    if (order_id is not None and order_id <= 0) or (
        customer_id is not None and customer_id <= 0
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="order_id/customer_id must be a positive integer",
        )

    recommendations: list[
        ProductRecommendation
    ] = await composition.products_service.recommend_products(
        user=current_user,
        order_id=order_id,
        customer_id=customer_id,
    )
    return [
        ProductRecommendationResponse(
            code=recommendation.code,
            name=recommendation.name,
            image_url=recommendation.image_url,
            description=recommendation.description,
            product_url=recommendation.product_url,
        )
        for recommendation in recommendations
    ]
