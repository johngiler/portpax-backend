from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """Default list pagination; clients may raise page_size up to max_page_size."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 500
