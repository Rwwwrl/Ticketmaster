from collections.abc import Iterator

import pytest
from fastapi import FastAPI, HTTPException, status
from ticketmaster.http.v1.dependencies import validate_user_jwt
from ticketmaster.models import User
from ticketmaster.schemas.dtos import BaseUserDTO
from ticketmaster.tests.factories import UserFactory


@pytest.fixture
def override_user_jwt(fastapi_app: FastAPI) -> Iterator[User]:
    user = UserFactory()

    async def _override() -> BaseUserDTO:
        return BaseUserDTO.from_sqlmodel(model=user)

    fastapi_app.dependency_overrides[validate_user_jwt] = _override
    yield user
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def invalid_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    def _raise() -> BaseUserDTO:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    fastapi_app.dependency_overrides[validate_user_jwt] = _raise
    yield
    fastapi_app.dependency_overrides.clear()
