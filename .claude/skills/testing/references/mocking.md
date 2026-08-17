# Mocking External Boundaries

Prefer real PostgreSQL and Redis fixtures. Mock external HTTP, AWS clients, authentication guards in endpoint tests, and explicit failure paths.

## FastAPI Dependency Overrides

Override the dependency on the shared app and clear all overrides after the test:

```python
@pytest.fixture
def bypass_admin_jwt(fastapi_app: FastAPI) -> Iterator[None]:
    fastapi_app.dependency_overrides[validate_admin_jwt] = lambda: None
    yield
    fastapi_app.dependency_overrides.clear()
```

Test the dependency itself separately by calling it directly.

## Monkeypatch

Patch the attribute used by the module under test. Use typed async replacements for async methods:

```python
async def _failing_get(*, name: str) -> bytes | None:
    raise RedisError("get failed")

monkeypatch.setattr(target=redis, name="get", value=_failing_get)
```

Use this for deterministic failure injection, cached singleton state, clocks, or module-bound clients. Restore manually only when the fixture cannot do it automatically.

## AsyncMock and MagicMock

Use `AsyncMock` for awaited methods and assert awaited arguments:

```python
client = AsyncMock()
client.admin_delete_user.return_value = {}

await delete_remote_user(client=client, pool_id="pool", username="alice")

client.admin_delete_user.assert_awaited_once_with(
    UserPoolId="pool",
    Username="alice",
)
```

Use `MagicMock` for synchronous factories or context-manager shells. Configure the mock before the action rather than mutating it midway through the behavior under test.

## Outbound HTTP

Use the `respx_mock` fixture for async HTTP clients:

```python
route = respx_mock.get(url="https://provider.test/events/1").mock(
    return_value=Response(status_code=200, json={"id": 1}),
)

result = await repository.get_event(_id=1)

assert result.id == 1
assert route.call_count == 1
```

Use `@respx.mock` for synchronous Lambda handler tests when that matches the existing file.

## Patching Module Singletons

Patch the object at its lookup site:

```python
with patch.object(target=handler, attribute="_kms", new=kms_stub):
    result = handler.lambda_handler(event=event, context=None)
```

Keep assertions outside the patch block when the mock remains available. Assert both the returned behavior and the important interaction; call assertions alone do not prove the user-visible outcome.

## Exceptions

Assert the narrow exception and relevant details:

```python
with pytest.raises(HTTPException) as exc_info:
    await validate_token(authorization="invalid")

assert exc_info.value.status_code == 401
```

Do not catch broad exceptions merely to make a test pass.
