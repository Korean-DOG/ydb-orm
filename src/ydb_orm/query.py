"""
Query builder для ydb-orm
"""

from typing import Type, TypeVar, Optional, List, Dict, Any, Union, Tuple, cast, Generic
from ydb_dataclass.queries import select_query, prepare_params
from .session import YDBSession
from .exceptions import NoResultFound, MultipleResultsFound, QueryError
from .utils.sql_builder import Condition

T = TypeVar('T')

class Query(Generic[T]):
    """Построитель запросов с цепочным интерфейсом"""

    def __init__(self, session: YDBSession, model: Type[T]):
        """
        Инициализация Query builder

        Args:
            session: Сессия YDBSession
            model: Класс модели (ydb_dataclass)
        """
        self._session = session
        self._model = model
        self._table_name = getattr(model, '__tablename__', model.__name__.lower())

        # Параметры запроса
        self._where_conditions: List[Condition] = []
        self._order_by: List[str] = []
        self._limit: Optional[int] = None
        self._offset: Optional[int] = None
        self._columns: Optional[List[str]] = None
        self._distinct: bool = False

    def filter(self, *conditions: Union[str, Condition]) -> 'Query[T]':
        """
        Добавление условий фильтрации

        Args:
            *conditions: Условия в виде строк или объектов Condition

        Returns:
            self для цепочных вызовов
        """
        for cond in conditions:
            if isinstance(cond, str):
                # Простое строковое условие
                self._where_conditions.append(Condition(cond))
            elif isinstance(cond, Condition):
                # Структурированное условие
                self._where_conditions.append(cond)
            else:
                raise QueryError(f"Неподдерживаемый тип условия: {type(cond)}")

        return self

    def filter_by(self, **kwargs) -> 'Query[T]':
        """
        Фильтрация по равенству полей (удобный синтаксис)

        Args:
            **kwargs: Пары поле=значение

        Returns:
            self для цепочных вызовов
        """
        for field, value in kwargs.items():
            self._where_conditions.append(Condition(field, "=", value))

        return self

    def order_by(self, *columns: str) -> 'Query[T]':
        """
        Указание сортировки

        Args:
            *columns: Поля для сортировки (можно с DESC/ASC)

        Returns:
            self для цепочных вызовов
        """
        self._order_by.extend(columns)
        return self

    def limit(self, limit: int) -> 'Query[T]':
        """
        Ограничение количества результатов

        Args:
            limit: Максимальное количество строк

        Returns:
            self для цепочных вызовов
        """
        self._limit = limit
        return self

    def offset(self, offset: int) -> 'Query[T]':
        """
        Смещение результатов (для пагинации)

        Args:
            offset: Количество пропускаемых строк

        Returns:
            self для цепочных вызовов
        """
        self._offset = offset
        return self

    def select(self, *columns: str) -> 'Query[T]':
        """
        Выбор конкретных колонок

        Args:
            *columns: Имена колонок для выборки

        Returns:
            self для цепочных вызовов
        """
        if not columns:
            raise QueryError("Не указаны колонки для выборки")

        self._columns = list(columns)
        return self

    def distinct(self) -> 'Query[T]':
        """
        Включение DISTINCT в запрос

        Returns:
            self для цепочных вызовов
        """
        self._distinct = True
        return self

    async def all(self) -> List[T]:
        """
        Выполнение запроса и возврат всех результатов

        Returns:
            Список объектов модели
        """
        sql, params = self._build_query()

        # Убеждаемся, что сессия существует
        if self._session._session is None:
            await self._session.connect()

        # Подготовка запроса (с кэшированием)
        if sql not in self._session._prepared_cache:
            # Подготавливаем запрос - метод prepare() есть у сессии YDB
            prepared = await self._session._session.prepare(sql)
            self._session._prepared_cache[sql] = prepared

        prepared = self._session._prepared_cache[sql]

        # Выполнение запроса
        async with self._session._transaction_context() as tx:
            result = await tx.execute(
                prepared,
                params,
                commit_tx=False
            )

        # Конвертация результатов в модели
        instances: List[T] = []
        for row in result[0].rows:
            instance = self._model.from_ydb_row(row)

            # Проверка identity map и сохранение
            pk_value = self._session._get_pk_value(instance)
            cached = self._session.get_from_identity_map(self._model, pk_value)

            if cached:
                instances.append(cast(T, cached))
            else:
                self._session._add_to_identity_map(instance)
                instances.append(cast(T, instance))

        return instances

    async def first(self) -> Optional[T]:
        """
        Возврат первого результата или None

        Returns:
            Первый объект модели или None
        """
        self._limit = 1
        results = await self.all()
        return cast(Optional[T], results[0] if results else None)

    async def one(self) -> T:
        """
        Возврат одного результата с проверкой уникальности

        Returns:
            Единственный объект модели

        Raises:
            NoResultFound: Если нет результатов
            MultipleResultsFound: Если больше одного результата
        """
        results = await self.all()

        if not results:
            raise NoResultFound(f"Запрос не вернул результатов для модели {self._model.__name__}")

        if len(results) > 1:
            raise MultipleResultsFound(
                f"Запрос вернул {len(results)} результатов, ожидался один для модели {self._model.__name__}"
            )

        return cast(T, results[0])

    async def one_or_none(self) -> Optional[T]:
        """
        Возврат одного результата или None

        Returns:
            Единственный объект модели или None

        Raises:
            MultipleResultsFound: Если больше одного результата
        """
        results = await self.all()

        if len(results) > 1:
            raise MultipleResultsFound(
                f"Запрос вернул {len(results)} результатов, ожидался один для модели {self._model.__name__}"
            )

        return cast(Optional[T], results[0] if results else None)

    async def count(self) -> int:
        """
        Подсчет количества строк, соответствующих условиям

        Returns:
            Количество строк
        """
        # Сохраняем текущие настройки колонок
        original_columns = self._columns

        try:
            # Выполняем COUNT запрос
            self._columns = ["COUNT(*) as count"]
            sql, params = self._build_query()

            if self._session._session is None:
                await self._session.connect()

            if sql not in self._session._prepared_cache:
                prepared = await self._session._session.prepare(sql)
                self._session._prepared_cache[sql] = prepared

            prepared = self._session._prepared_cache[sql]

            async with self._session._transaction_context() as tx:
                result = await tx.execute(
                    prepared,
                    params,
                    commit_tx=False
                )

            # Извлекаем значение COUNT
            if result[0].rows:
                count_row = result[0].rows[0]
                # Пробуем разные способы получить значение
                if hasattr(count_row, 'count'):
                    count_value = count_row.count
                    if hasattr(count_value, 'uint64_value'):
                        return count_value.uint64_value
                    elif hasattr(count_value, 'int64_value'):
                        return count_value.int64_value
                    elif hasattr(count_value, 'int_value'):
                        return count_value.int_value
                    else:
                        # Пробуем преобразовать в int
                        try:
                            return int(count_value)
                        except (TypeError, ValueError):
                            return 0

            return 0

        finally:
            # Восстанавливаем настройки колонок
            self._columns = original_columns

    def _build_query(self) -> Tuple[str, Dict[str, Any]]:
        """
        Построение SQL запроса и параметров

        Returns:
            Кортеж (SQL запрос, параметры)
        """
        # Преобразование условий в формат для ydb_dataclass.queries
        where_dict = {}
        for condition in self._where_conditions:
            if condition.operator == "=":
                where_dict[condition.field] = condition.value
            else:
                # Для сложных условий используем строковый формат
                key = f"{condition.field}_{condition.operator}"
                where_dict[key] = condition.value

        # Генерация SQL
        sql = select_query(
            table_name=self._table_name,
            ydb_fields=self._model._ydb_fields if not self._columns else None,
            where=where_dict if where_dict else None,
            order_by=self._order_by if self._order_by else None,
            limit=self._limit,
            offset=self._offset,
            columns=self._columns
        )

        # Добавление DISTINCT если нужно
        if self._distinct:
            sql = sql.replace("SELECT", "SELECT DISTINCT", 1)

        # Подготовка параметров
        params = prepare_params({}, where_dict) if where_dict else {}

        return sql, params

    # Магические методы для удобства
    def __getattr__(self, name: str) -> Any:
        """
        Поддержка цепочек вида .filter_by_name("value")
        """
        if name.startswith('filter_by_'):
            field_name = name[10:]  # Убираем 'filter_by_'

            def filter_by_value(value: Any) -> 'Query[T]':
                self._where_conditions.append(Condition(field_name, "=", value))
                return self

            return filter_by_value

        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")