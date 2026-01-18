"""
YDB-ORM: ORM-слой для YDB на основе ydb-dataclass

Основные компоненты:
- YDBSession: Управление сессиями и транзакциями
- Query: Построитель запросов
- relationships: Система отношений между моделями
"""

from .session import YDBSession, AsyncSessionContext
from .query import Query
from .relationships import relationship, one_to_many, many_to_one, RelationshipProxy
from .registry import register_model, ModelRegistry, default_registry
from .exceptions import YDBORMError, NoResultFound, MultipleResultsFound, RelationshipError

__version__ = "0.2.0"
__all__ = [
    "YDBSession",
    "AsyncSessionContext",
    "Query",
    "relationship",
    "one_to_many",
    "many_to_one",
    "RelationshipProxy",
    "register_model",
    "ModelRegistry",
    "default_registry",
    "YDBORMError",
    "NoResultFound",
    "MultipleResultsFound",
    "RelationshipError",
]