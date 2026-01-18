"""
Кастомные исключения для ydb-orm
"""

class YDBORMError(Exception):
    """Базовое исключение для всех ошибок ydb-orm"""
    pass

class NoResultFound(YDBORMError):
    """Исключение, когда запрос не вернул результатов"""
    pass

class MultipleResultsFound(YDBORMError):
    """Исключение, когда запрос вернул несколько результатов, а ожидался один"""
    pass

class SessionError(YDBORMError):
    """Ошибка сессии (не подключена, уже закрыта и т.д.)"""
    pass

class TransactionError(YDBORMError):
    """Ошибка транзакции"""
    pass

class QueryError(YDBORMError):
    """Ошибка построения или выполнения запроса"""
    pass

class RelationshipError(YDBORMError):
    """Ошибка в отношениях между моделями"""
    pass