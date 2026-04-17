# Mock Patterns

## Basic Patch

Configure mocks completely in the `patch()` call. Assertions outside the `with` block.

```python
from unittest.mock import patch

with patch(
    "ticketmaster.services.OrderService.create_order",
    return_value=mock_order,
) as mock_create:
    response = await async_client.post(url="/v1/orders/", json=payload)

assert response.status_code == 201
mock_create.assert_called_once()
```

Never configure mocks after creation:

```python
# WRONG
with patch(...) as mock_create:
    mock_create.return_value = mock_order  # Don't do this
```

## Async Mock

```python
from unittest.mock import AsyncMock, patch

with patch(
    "path.to.async_function",
    new_callable=AsyncMock,
    return_value=expected_result,
) as mock_func:
    response = await async_client.get(url="/endpoint")

mock_func.assert_called_once()
```

## Multiple Mocks

Use parenthesized `with` statement:

```python
with (
    patch("path.to.ServiceA.method", return_value=result_a) as mock_a,
    patch("path.to.ServiceB.method", return_value=result_b) as mock_b,
):
    response = await async_client.post(url="/endpoint", json=payload)

assert mock_a.call_count == 1
assert mock_b.call_args.kwargs["param"] == expected_value
```

## Side Effects

```python
with patch(
    "path.to.function",
    side_effect=[first_call_result, second_call_result],
) as mock_func:
    # First call returns first_call_result
    # Second call returns second_call_result
    ...
```

## Verifying Call Arguments

```python
mock_create_order.assert_called_once()

call_kwargs = mock_create_order.call_args.kwargs
assert call_kwargs["user_id"] == test_user.id
assert call_kwargs["product_id"] == product_id

assert mock_func.call_count == 3
```
