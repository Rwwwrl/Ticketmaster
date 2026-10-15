from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from ticketmaster.admin.http.dependencies import validate_admin_jwt


@pytest.fixture
def bypass_admin_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    fastapi_app.dependency_overrides[validate_admin_jwt] = lambda: None
    yield
    fastapi_app.dependency_overrides.clear()
