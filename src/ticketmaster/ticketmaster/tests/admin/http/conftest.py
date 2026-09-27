from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from libs.aws.session import aws_session
from ticketmaster.admin.http.dependencies import validate_admin_jwt


@pytest.fixture
def bypass_admin_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    fastapi_app.dependency_overrides[validate_admin_jwt] = lambda: None
    yield
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def mock_s3(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    s3 = AsyncMock()

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=s3)
    cm.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(aws_session, "client", MagicMock(return_value=cm))
    return s3
