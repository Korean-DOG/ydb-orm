# YDB-ORM

ORM-слой для YDB на основе `ydb-dataclass` с явными типами YDB.

## Особенности

- ✅ Явная типизация YDB в аннотациях
- ✅ Асинхронный API из коробки
- ✅ Цепочный Query builder (похожий на SQLAlchemy)
- ✅ Identity Map и кэширование prepared statements
- ✅ Полная совместимость с `ydb-dataclass`

## Установка

```bash
pip install git+https://github.com/Korean-DOG/ydb-orm.git# ydb-orm
```
**Быстрый старт**
1. Определение моделей
```python
from typing import Optional
from ydb_dataclass import ydb_dataclass, YDB
from datetime import datetime

@ydb_dataclass
class User:
    __tablename__ = "users"
    
    id: YDB.int64
    username: YDB.utf8
    email: Optional[YDB.utf8]
    age: Optional[YDB.uint64]
    is_active: YDB.bool = True
    created_at: YDB.timestamp = lambda: int(datetime.now().timestamp() * 1_000_000)
```
2. Создание сессии
```python
import ydb
from ydb_orm import YDBSession

# Создание драйвера YDB
driver = ydb.Driver(
    endpoint="grpcs://ydb.serverless.yandexcloud.net:2135",
    database="/ru-central1/b1g...",
    credentials=ydb.iam.ServiceAccountCredentials.from_file("sa-key.json")
)
driver.wait(timeout=5)

# Создание сессии
session = YDBSession(driver)
```
3. CRUD операции
```python
# Создание
async def create_user():
    user = User(
        id=1,
        username="john_doe",
        email="john@example.com",
        age=25
    )
    
    await session.add(user)  # INSERT
    # или await session.add(user, upsert=True) для UPSERT

# Чтение
async def get_users():
    # Все пользователи
    users = await session.query(User).all()
    
    # С фильтрацией
    active_users = await (session.query(User)
                         .filter_by(is_active=True)
                         .filter(User.age >= 18)
                         .order_by("created_at DESC")
                         .limit(10)
                         .all())
    
    # Один пользователь
    user = await session.query(User).filter_by(id=1).first()
    
    # Проверка на уникальность
    try:
        user = await session.query(User).filter_by(username="john_doe").one()
    except NoResultFound:
        print("Пользователь не найден")
    except MultipleResultsFound:
        print("Найдено несколько пользователей")
    
    # Подсчет
    count = await session.query(User).filter_by(is_active=True).count()

# Обновление
async def update_user():
    user = await session.query(User).filter_by(id=1).first()
    if user:
        user.username = "john_updated"
        await session.add(user, upsert=True)

# Удаление
async def delete_user():
    user = await session.query(User).filter_by(id=1).first()
    if user:
        await session.delete(user)
```
4. Транзакции
```python
async def transfer_points(from_user_id: int, to_user_id: int, points: int):
    async with session.transaction():
        from_user = await session.query(User).filter_by(id=from_user_id).first()
        to_user = await session.query(User).filter_by(id=to_user_id).first()
        
        if from_user.points < points:
            raise ValueError("Недостаточно points")
        
        from_user.points -= points
        to_user.points += points
        
        await session.add(from_user, upsert=True)
        await session.add(to_user, upsert=True)
        
        # Автоматический коммит при успешном выполнении
        # Автоматический rollback при исключении
```
**Расширенный Query API**<br>
*Условия фильтрации*
```python
from ydb_orm.utils.sql_builder import gt, lt, in_, like

# Разные способы фильтрации
users = await (session.query(User)
               .filter(User.age > 18)
               .filter_by(is_active=True)
               .filter(gt("age", 21))
               .filter(in_("id", [1, 2, 3]))
               .filter(like("username", "john%"))
               .all())

# Цепочки вида .filter_by_<field>
users = await session.query(User).filter_by_age(25).filter_by_is_active(True).all()
```
Сортировка и пагинация
```python
# Пагинация с сортировкой
page1 = await (session.query(User)
               .order_by("created_at DESC", "username ASC")
               .limit(20)
               .offset(0)
               .all())

page2 = await (session.query(User)
               .order_by("created_at DESC", "username ASC")
               .limit(20)
               .offset(20)
               .all())
```
Выбор конкретных колонок
```python
# Только нужные колонки
users_data = await (session.query(User)
                    .select("id", "username", "email")
                    .filter_by(is_active=True)
                    .all())

# DISTINCT запросы
unique_ages = await (session.query(User)
                     .select("age")
                     .distinct()
                     .order_by("age")
                     .all())
```
🚀 Пример использования отношений
```python
from typing import List, Optional
from ydb_dataclass import ydb_dataclass, YDB
from ydb_orm import relationship, one_to_many, register_model
import asyncio

# Модели с отношениями
@ydb_dataclass
@register_model
class User:
    __tablename__ = "users"
    __primary_key__ = "id"
    
    id: YDB.int64
    username: YDB.utf8
    email: YDB.utf8
    
    # Отношение один-ко-многим (ленивое по умолчанию)
    orders: List["Order"] = relationship(
        target_model="Order",
        foreign_key="user_id",
        backref="user",
        order_by="created_at DESC"
    )
    
    # Альтернативный синтаксис
    # orders = one_to_many("Order", foreign_key="user_id")

@ydb_dataclass
@register_model
class Order:
    __tablename__ = "orders"
    __primary_key__ = "id"
    
    id: YDB.int64
    user_id: YDB.int64
    amount: YDB.decimal(10, 2)
    created_at: YDB.timestamp
    
    # Обратная ссылка автоматически создается через backref
    # user = many_to_one("User", foreign_key="user_id")

async def example():
    # Создаём драйвер и сессию (как ранее)
    session = YDBSession(driver)
    
    # Находим пользователя с заказами (ленивая загрузка)
    user = await session.query(User).filter_by(id=1).first()
    
    # Попытка доступа к заказам вызовет ошибку без сессии
    try:
        orders = user.orders  # Ошибка: ленивая загрузка требует сессии
    except RelationshipError as e:
        print(f"Ленивая загрузка не работает: {e}")
    
    # Жадная загрузка с помощью .include()
    # (нужно добавить метод .include() в Query)
    user_with_orders = await (session.query(User)
                             .include(User.orders)
                             .filter_by(id=1)
                             .first())
    
    # Теперь заказы уже загружены
    for order in user_with_orders.orders:
        print(f"Заказ {order.id} на сумму {order.amount}")
    
    # Или явная загрузка через сессию
    user = await session.query(User).filter_by(id=1).first()
    orders_proxy = user.orders  # Это RelationshipProxy
    orders = await orders_proxy()  # Явная загрузка
    
    await session.close()

# Запуск примера
if __name__ == "__main__":
    asyncio.run(example())
```









