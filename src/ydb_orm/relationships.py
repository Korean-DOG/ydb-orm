"""
Система отношений между моделями (relationships)
"""

from typing import Type, TypeVar, Optional, Union, Any
from dataclasses import dataclass

from .exceptions import RelationshipError
from .registry import default_registry

T = TypeVar('T')

@dataclass
class RelationshipInfo:
    """Информация об отношении между моделями"""

    target_model: Union[str, Type[Any]]
    backref: Optional[str] = None
    foreign_key: Optional[str] = None
    primary_key: Optional[str] = None
    lazy: bool = True

    secondary: Optional[str] = None
    secondary_foreign_keys: Optional[tuple[str, str]] = None

    order_by: Optional[str] = None
    cascade: Optional[str] = None
    single_parent: bool = False

    def __post_init__(self):
        if not self.foreign_key and not self.secondary:
            raise RelationshipError(
                "Для отношения должен быть указан foreign_key или secondary таблица"
            )


class RelationshipProxy:
    """Прокси для ленивой загрузки отношений"""

    def __init__(
        self,
        parent_instance: Any,
        relationship_info: RelationshipInfo,
        session: Optional[Any] = None
    ):
        self._parent = parent_instance
        self._info = relationship_info
        self._session = session
        self._loaded = False
        self._value: Optional[Any] = None

    async def load(self) -> None:
        """Загрузка связанных данных"""
        if self._loaded or not self._session:
            return

        target_model = self._resolve_target_model()
        parent_pk = self._get_parent_primary_key()

        query = self._session.query(target_model)

        if self._info.secondary:
            await self._load_many_to_many(query, parent_pk)
        else:
            await self._load_one_to_many(query, parent_pk)

        self._loaded = True

    def _resolve_target_model(self) -> Type[Any]:
        """Разрешение имени модели в класс"""
        if isinstance(self._info.target_model, str):
            model = default_registry.get_model(self._info.target_model)
            if not model:
                raise RelationshipError(
                    f"Модель '{self._info.target_model}' не найдена в реестре"
                )
            return model
        return self._info.target_model

    def _get_parent_primary_key(self) -> Any:
        """Получение значения первичного ключа родителя"""
        parent_model = type(self._parent)
        pk_field = getattr(parent_model, '_primary_key', 'id')
        return getattr(self._parent, pk_field)

    async def _load_one_to_many(
        self,
        query: Any,
        parent_pk: Any
    ) -> None:
        """Загрузка для отношений один-ко-многим/многие-к-одному"""
        if not self._info.foreign_key:
            raise RelationshipError("Для загрузки отношения нужен foreign_key")

        target_model = query._model
        target_fields = getattr(target_model, '_ydb_fields', {})

        if self._info.foreign_key in target_fields:
            query = query.filter_by(**{self._info.foreign_key: parent_pk})

        if self._info.order_by:
            query = query.order_by(self._info.order_by)

        if self._info.backref and 'uselist' in self._info.backref:
            self._value = await query.all()
        else:
            self._value = await query.first()

    async def _load_many_to_many(
        self,
        query: Any,
        parent_pk: Any
    ) -> None:
        """Загрузка для отношений многие-ко-многим"""
        raise NotImplementedError("Отношения многие-ко-многим пока не реализованы")

    def __get__(self, instance, owner):
        """Дескриптор для доступа к значению"""
        if instance is None:
            return self

        if self._loaded:
            return self._value

        raise RelationshipError(
            "Ленивая загрузка требует активной сессии. "
            "Используйте жадную загрузку через .include() или "
            "убедитесь что у отношения есть доступ к сессии."
        )

    async def __call__(self) -> Any:
        """Асинхронный вызов для явной загрузки"""
        await self.load()
        return self._value


def relationship(
    target_model: Union[str, Type[Any]],
    backref: Optional[str] = None,
    foreign_key: Optional[str] = None,
    primary_key: Optional[str] = None,
    lazy: bool = True,
    secondary: Optional[str] = None,
    order_by: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Фабрика для создания отношений между моделями
    """
    info = RelationshipInfo(
        target_model=target_model,
        backref=backref,
        foreign_key=foreign_key,
        primary_key=primary_key,
        lazy=lazy,
        secondary=secondary,
        order_by=order_by,
        **kwargs
    )

    return RelationshipProxy(None, info)


def one_to_many(
    target_model: Union[str, Type[Any]],
    foreign_key: str,
    backref: Optional[str] = None,
    **kwargs
) -> Any:
    """Создание отношения один-ко-многим"""
    return relationship(
        target_model=target_model,
        foreign_key=foreign_key,
        backref=backref or f"parent_{target_model.__name__.lower()}",
        **kwargs
    )


def many_to_one(
    target_model: Union[str, Type[Any]],
    foreign_key: str,
    backref: Optional[str] = None,
    **kwargs
) -> Any:
    """Создание отношения многие-к-одному"""
    return relationship(
        target_model=target_model,
        foreign_key=foreign_key,
        backref=backref or f"children_{target_model.__name__.lower()}s",
        **kwargs
    )