"""Shared pagination contract for list endpoints.

Every list endpoint is bounded: unbounded ``SELECT ...`` over users, documents,
or conversations makes response size and query cost grow with the data. The
unpaginated row count is exposed as ``X-Total-Count`` so a client can tell that
more rows exist without changing the response body.
"""

from typing import Annotated

from fastapi import Query, Response

DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 200

LimitQuery = Annotated[
    int,
    Query(
        ge=1,
        le=MAX_PAGE_SIZE,
        description=f"Maximum rows to return (default {DEFAULT_PAGE_SIZE})",
    ),
]
OffsetQuery = Annotated[
    int,
    Query(ge=0, description="Rows to skip before returning the page"),
]

TOTAL_COUNT_HEADER = "X-Total-Count"


def set_total_count_header(response: Response, total: int) -> None:
    """Expose the unpaginated row count of a list endpoint."""
    response.headers[TOTAL_COUNT_HEADER] = str(total)
