from enum import Enum

from sqlalchemy import String, TypeDecorator
from sqlalchemy.engine import Dialect


class EnumString[EnumT: Enum](TypeDecorator[EnumT]):
    """VARCHAR column that round-trips a Python enum via its value.

    The physical column stays plain ``VARCHAR`` (no native DB enum, no
    ``CHECK`` constraint, no length). On load, the raw string is coerced
    back to the declared enum class so ORM attributes match their typed
    annotation instead of carrying bare strings.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_class: type[EnumT]) -> None:
        super().__init__()
        # NOTE @sosov: Must stay public (no underscore). SQLAlchemy's compiled-query
        # cache builds this type's static cache key by introspecting __init__ params
        # and looking each name up in self.__dict__ — attributes prefixed with `_`
        # are skipped. Without this, two EnumString(EnumA) / EnumString(EnumB)
        # instances would collide on the same cache entry.
        self.enum_class = enum_class

    def process_bind_param(self, value: EnumT | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return value.value

    def process_result_value(self, value: str | None, dialect: Dialect) -> EnumT | None:
        if value is None:
            return None
        return self.enum_class(value)
