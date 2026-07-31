from app.application.ports import Life365APIGateway, ProductsGateway
from app.application.services.products_service import ProductsService
from app.infrastructure.data_mapper import DATABASE_URL, ProductsDataMapper
from app.infrastructure.life365_portal_api import Life365PortalAPI

products_gateway: ProductsGateway = ProductsDataMapper(DATABASE_URL)
life365_api_gateway: Life365APIGateway = Life365PortalAPI()
products_service: ProductsService = ProductsService(
    products_gateway, life365_api_gateway
)
