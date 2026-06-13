from collections.abc import AsyncGenerator
from datetime import date
from urllib.parse import quote_plus

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

from app.config import settings


Base = declarative_base()


def _build_database_url() -> str:
    password = quote_plus(settings.MYSQL_PASSWORD)
    return (
        f"mysql+asyncmy://{settings.MYSQL_USER}:{password}"
        f"@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
        "?charset=utf8mb4"
    )


engine = create_async_engine(_build_database_url(), echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class SalesOrder(Base):
    __tablename__ = "sales_orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False)
    product_category: Mapped[str] = mapped_column(String(128), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)

    reviews: Mapped[list["Review"]] = relationship(back_populates="order")


class Review(Base):
    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sales_orders.order_id"),
        nullable=False,
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(32), nullable=False)

    order: Mapped["SalesOrder"] = relationship(back_populates="reviews")


async def init_mysql() -> None:
    import app.models.conversation  # noqa: F401 — register ORM tables

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
