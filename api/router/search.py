from fastapi import APIRouter

from api.controller.search import universal_search_controller

search_router = APIRouter(prefix="/search", tags=["Search"])

search_router.add_api_route(
    "",
    endpoint=universal_search_controller,
    methods=["GET"],
    response_model=dict,
    summary="Universal search across core entities",
)

