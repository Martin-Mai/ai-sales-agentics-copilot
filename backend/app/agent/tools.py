"""Agent 工具定义：SQLTool 与 VectorTool。"""

import asyncio
from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Callable, Literal, Optional, Type

from pydantic import BaseModel, Field
from sqlalchemy import extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import ALLOWED_COLUMNS
from app.database.chroma_client import embedding_model, get_comments_collection
from app.database.mysql_client import SalesOrder

_OPERATOR_ALIASES = {
    "==": "eq",
    "!=": "ne",
    ">": "gt",
    "<": "lt",
    ">=": "ge",
    "<=": "le",
    "eq": "eq",
    "ne": "ne",
    "gt": "gt",
    "lt": "lt",
    "ge": "ge",
    "le": "le",
    "month": "month",
    "year": "year",
    "day": "day",
    "contains": "contains",
}


class BaseTool(ABC):
    name: str
    description: str
    input_schema: Type[BaseModel]

    @abstractmethod
    async def run(self, input_data: BaseModel) -> Any:
        pass


class SQLIntent(BaseModel):
    operation: Literal["sum", "mean", "count", "min", "max"] = Field(
        ..., description="聚合操作"
    )
    target_column: Literal["revenue", "quantity"] = Field(
        ..., description="目标统计列"
    )
    aggregation: Optional[str] = Field(None, description="别名或辅助聚合描述")
    group_by: Optional[
        Literal["region", "product_category", "channel", "month", "order_date"]
    ] = Field(None, description="分组维度")
    filters: list[dict] = Field(
        default_factory=list,
        description="过滤条件，格式如 [{'column': 'region', 'operator': '==', 'value': '华东'}]",
    )


class VectorQuery(BaseModel):
    query: str = Field(..., description="检索评论的语义查询字符串")
    top_k: int = Field(5, description="检索匹配的最高评论条数")


class SQLTool(BaseTool):
    name = "sql_tool"
    description = "基于 SQLAlchemy Core 的安全结构化销售数据查询"
    input_schema = SQLIntent

    _AGG_FUNCS: dict[str, Callable] = {
        "sum": func.sum,
        "mean": func.avg,
        "count": func.count,
        "min": func.min,
        "max": func.max,
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def _normalize_operator(raw: str | None) -> str:
        if raw is None:
            raise ValueError("过滤条件缺少 operator")
        op = _OPERATOR_ALIASES.get(raw.strip())
        if op is None:
            raise ValueError(f"不支持的操作符: {raw}")
        return op

    @staticmethod
    def _validate_filter_column(column: str) -> None:
        if column not in ALLOWED_COLUMNS:
            raise ValueError(f"列 {column} 不在白名单中")

    def _build_filter_clause(self, column_name: str, operator: str, value: Any):
        self._validate_filter_column(column_name)
        column = getattr(SalesOrder, column_name)

        if operator == "eq":
            return column == value
        if operator == "ne":
            return column != value
        if operator == "gt":
            return column > value
        if operator == "lt":
            return column < value
        if operator == "ge":
            return column >= value
        if operator == "le":
            return column <= value
        if operator == "month":
            return extract("month", column) == int(value)
        if operator == "year":
            return extract("year", column) == int(value)
        if operator == "day":
            return extract("day", column) == int(value)
        if operator == "contains":
            return column.contains(str(value))
        raise ValueError(f"不支持的操作符: {operator}")

    @staticmethod
    def _normalize_filter_value(column_name: str, operator: str, value: Any) -> Any:
        if column_name != "order_date" or value is None:
            return value
        if operator in ("month", "year", "day"):
            if isinstance(value, str):
                return int(value)
            return value
        if isinstance(value, str):
            return date.fromisoformat(value)
        return value

    def _apply_filters(self, stmt, filters: list[dict]):
        for f in filters:
            column_name = f.get("column")
            if not column_name:
                raise ValueError("过滤条件缺少 column")
            operator = self._normalize_operator(f.get("operator") or f.get("op"))
            value = self._normalize_filter_value(column_name, operator, f.get("value"))
            clause = self._build_filter_clause(column_name, operator, value)
            stmt = stmt.where(clause)
        return stmt

    async def run(self, input_data: BaseModel) -> Any:
        if not isinstance(input_data, SQLIntent):
            input_data = SQLIntent.model_validate(input_data)

        agg_fn = self._AGG_FUNCS[input_data.operation]
        target_col = getattr(SalesOrder, input_data.target_column)

        if input_data.group_by == "month":
            month_col = extract("month", SalesOrder.order_date)
            stmt = (
                select(month_col, agg_fn(target_col))
                .group_by(month_col)
                .order_by(month_col)
            )
            stmt = self._apply_filters(stmt, input_data.filters)
            result = await self.session.execute(stmt)
            rows = result.all()
            return {
                f"{int(row[0])}月": float(row[1]) if row[1] is not None else 0.0
                for row in rows
            }

        if input_data.group_by == "order_date":
            date_col = SalesOrder.order_date
            stmt = (
                select(date_col, agg_fn(target_col))
                .group_by(date_col)
                .order_by(date_col)
            )
            stmt = self._apply_filters(stmt, input_data.filters)
            result = await self.session.execute(stmt)
            rows = result.all()
            return {
                str(row[0]): float(row[1]) if row[1] is not None else 0.0
                for row in rows
            }

        if input_data.group_by:
            group_col = getattr(SalesOrder, input_data.group_by)
            stmt = select(group_col, agg_fn(target_col)).group_by(group_col)
            stmt = self._apply_filters(stmt, input_data.filters)
            result = await self.session.execute(stmt)
            rows = result.all()
            return {
                str(row[0]): float(row[1]) if row[1] is not None else 0.0
                for row in rows
            }

        stmt = select(agg_fn(target_col))
        stmt = self._apply_filters(stmt, input_data.filters)
        result = await self.session.execute(stmt)
        value = result.scalar()
        if value is None:
            return 0 if input_data.operation == "count" else 0.0
        if input_data.operation == "count":
            return int(value)
        return float(value)


class VectorTool(BaseTool):
    name = "vector_tool"
    description = "基于 ChromaDB 的用户评论语义检索"
    input_schema = VectorQuery

    async def run(self, input_data: BaseModel) -> Any:
        if not isinstance(input_data, VectorQuery):
            input_data = VectorQuery.model_validate(input_data)

        embeddings = await embedding_model.embed_texts([input_data.query])
        collection = await get_comments_collection()

        def _query_sync() -> list[str]:
            results = collection.query(
                query_embeddings=embeddings,
                n_results=input_data.top_k,
            )
            docs = results.get("documents", [[]])[0]
            return docs if docs else ["未找到相关评论"]

        return await asyncio.to_thread(_query_sync)
