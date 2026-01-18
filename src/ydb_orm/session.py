"""
Реализация сессии и управления транзакциями
"""

from contextlib import asynccontextmanager
from typing import Type, TypeVar, Optional, Any, Dict, AsyncIterator
import ydb
from ydb_dataclass.queries import (
    insert_query, delete_query, upsert_query, prepare_params
)

from .query import Query
from .exceptions import SessionError

T = TypeVar('T')

class YDBSession:
    """Сессия для работы с YDB через ORM"""

    def __init__(self, driver: ydb.Driver):
        """
        Инициализация сессии

        Args:
            driver: Драйвер YDB (уже подключенный к базе)
        """
        self._driver = driver
        self._session: Optional[Any] = None
        self._tx: Optional[Any] = None
        self._identity_map: Dict[Type, Dict[Any, Any]] = {}
        self._prepared_cache: Dict[str, Any] = {}

    async def __aenter__(self):
        """Асинхронный контекстный менеджер"""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие сессии при выходе из контекста"""
        await self.close()

    async def connect(self):
        """Создание сессии YDB"""
        try:
            table_client = self._driver.table_client
            self._session = await table_client.session().create()
        except Exception as e:
            raise SessionError(f"Не удалось создать сессию: {e}") from e

    async def close(self):
        """Закрытие сессии и очистка ресурсов"""
        if self._session:
            try:
                if hasattr(self._session, 'close'):
                    await self._session.close()
                elif hasattr(self._session, 'stop'):
                    await self._session.stop()
            except Exception:
                pass
            finally:
                self._session = None
                self._tx = None

        self._identity_map.clear()
        self._prepared_cache.clear()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Any]:
        """
        Контекстный менеджер для транзакций

        Yields:
            Объект транзакции YDB
        """
        if not self._session:
            await self.connect()

        if self._tx is not None:
            yield self._tx
            return

        try:
            self._tx = self._session.transaction()
            await self._tx.begin()
            yield self._tx
            await self._tx.commit()
        except Exception as e:
            if self._tx:
                try:
                    await self._tx.rollback()
                except:
                    pass
            raise
        finally:
            self._tx = None

    def query(self, model: Type[T]) -> Query[T]:
        """
        Создание Query builder для модели

        Args:
            model: Класс модели (ydb_dataclass)

        Returns:
            Query builder
        """
        return Query(self, model)

    async def add(self, instance: Any, *, upsert: bool = False):
        """
        Добавление или обновление объекта в базе

        Args:
            instance: Экземпляр модели для сохранения
            upsert: Если True, использовать UPSERT вместо INSERT
        """
        model_type = type(instance)
        table_name = getattr(instance, '__tablename__', model_type.__name__.lower())

        if upsert:
            sql = upsert_query(table_name, model_type._ydb_fields)
        else:
            sql = insert_query(table_name, model_type._ydb_fields)

        if sql not in self._prepared_cache:
            if not self._session:
                await self.connect()

            try:
                prepared = await self._session.prepare(sql)
                self._prepared_cache[sql] = prepared
            except Exception as e:
                raise SessionError(f"Ошибка подготовки запроса: {e}") from e

        prepared = self._prepared_cache[sql]

        async with self.transaction() as tx:
            try:
                await tx.execute(
                    prepared,
                    instance.to_ydb_dict(),
                    commit_tx=False
                )
            except Exception as e:
                raise SessionError(f"Ошибка выполнения запроса: {e}") from e

        self._add_to_identity_map(instance)

    async def delete(self, instance: Any):
        """
        Удаление объекта из базы

        Args:
            instance: Экземпляр модели для удаления
        """
        model_type = type(instance)
        table_name = getattr(instance, '__tablename__', model_type.__name__.lower())

        pk_fields = getattr(model_type, '_primary_keys', ['id'])
        where_conditions = {}

        for pk_field in pk_fields:
            where_conditions[pk_field] = getattr(instance, pk_field)

        sql = delete_query(table_name, where_conditions)

        if sql not in self._prepared_cache:
            if not self._session:
                await self.connect()

            try:
                prepared = await self._session.prepare(sql)
                self._prepared_cache[sql] = prepared
            except Exception as e:
                raise SessionError(f"Ошибка подготовки запроса: {e}") from e

        prepared = self._prepared_cache[sql]

        async with self.transaction() as tx:
            try:
                await tx.execute(
                    prepared,
                    prepare_params({}, where_conditions),
                    commit_tx=False
                )
            except Exception as e:
                raise SessionError(f"Ошибка выполнения запроса: {e}") from e

        self._remove_from_identity_map(instance)

    def _add_to_identity_map(self, instance: Any):
        """Добавление объекта в identity map"""
        model_type = type(instance)
        pk_value = self._get_pk_value(instance)

        if model_type not in self._identity_map:
            self._identity_map[model_type] = {}

        self._identity_map[model_type][pk_value] = instance

    def _remove_from_identity_map(self, instance: Any):
        """Удаление объекта из identity map"""
        model_type = type(instance)
        pk_value = self._get_pk_value(instance)

        if model_type in self._identity_map:
            self._identity_map[model_type].pop(pk_value, None)

    def _get_pk_value(self, instance: Any) -> Any:
        """Получение значения первичного ключа"""
        pk_fields = getattr(type(instance), '_primary_keys', ['id'])

        if len(pk_fields) == 1:
            return getattr(instance, pk_fields[0])

        return tuple(getattr(instance, field) for field in pk_fields)

    def get_from_identity_map(self, model: Type[T], pk_value: Any) -> Optional[T]:
        """Получение объекта из identity map по первичному ключу"""
        if model in self._identity_map:
            return self._identity_map[model].get(pk_value)
        return None