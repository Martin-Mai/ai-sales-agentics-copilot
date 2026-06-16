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
from app.database.mysql_client import Review, SalesOrder

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


async def fetch_order_date_range(session: AsyncSession) -> tuple[date | None, date | None]:
    result = await session.execute(
        select(func.min(SalesOrder.order_date), func.max(SalesOrder.order_date))
    )
    min_date, max_date = result.one()
    return min_date, max_date


async def fetch_filtered_order_date_range(
    session: AsyncSession,
    filters: list[dict],
) -> tuple[date | None, date | None]:
    stmt = select(func.min(SalesOrder.order_date), func.max(SalesOrder.order_date))
    if filters:
        tool = SQLTool(session)
        stmt = tool._apply_filters(stmt, filters)
    result = await session.execute(stmt)
    min_date, max_date = result.one()
    return min_date, max_date


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


def format_review_line(
    *,
    region: str,
    order_date,
    channel: str,
    product_category: str,
    sentiment: str,
    rating: int,
    comment: str,
) -> str:
    date_str = order_date.isoformat() if hasattr(order_date, "isoformat") else str(order_date)
    return (
        f"[{region}|{date_str}|{channel}|{product_category}|"
        f"{sentiment}|{rating}星] {comment}"
    )


def build_reviews_scope_note(sql_filters: list[dict], analysis_time_scope: str) -> str:
    if sql_filters:
        parts = []
        for f in sql_filters:
            col = f.get("column", "")
            op = f.get("operator", "")
            val = f.get("value", "")
            if col == "order_date" and op == "year":
                parts.append(f"{val}年")
            elif col == "order_date" and op == "month":
                parts.append(f"{val}月")
            elif col == "region":
                parts.append(f"区域={val}")
            elif col == "channel":
                parts.append(f"渠道={val}")
            elif col == "product_category":
                parts.append(f"品类={val}")
        filter_desc = "、".join(parts) if parts else "与 SQL 相同的过滤条件"
        return f"以下评论来自与 SQL 统计一致的数据范围（{filter_desc}），已标注区域/日期/渠道，可直接用于归因。"
    if analysis_time_scope and "用户未指定" not in analysis_time_scope:
        return f"以下评论来自同一分析时间范围内的订单（{analysis_time_scope}），已标注区域/日期/渠道。"
    return "以下评论来自当前数据集，已标注区域/日期/渠道/品类。"


async def fetch_reviews_from_mysql(
    session: AsyncSession,
    filters: list[dict],
    top_k: int = 5,
) -> list[str]:
    """从 MySQL 按 SQL 过滤条件拉取评论，并附带订单维度标签。"""
    stmt = (
        select(
            Review.comment,
            Review.rating,
            Review.sentiment,
            SalesOrder.region,
            SalesOrder.order_date,
            SalesOrder.channel,
            SalesOrder.product_category,
        )
        .join(SalesOrder, Review.order_id == SalesOrder.order_id)
    )
    if filters:
        tool = SQLTool(session)
        stmt = tool._apply_filters(stmt, filters)
    stmt = stmt.limit(top_k)
    result = await session.execute(stmt)
    rows = result.all()
    if not rows:
        return []
    return [
        format_review_line(
            region=row.region,
            order_date=row.order_date,
            channel=row.channel,
            product_category=row.product_category,
            sentiment=row.sentiment,
            rating=row.rating,
            comment=row.comment,
        )
        for row in rows
    ]


async def _enrich_order_ids_from_mysql(
    session: AsyncSession,
    order_ids: list[str],
) -> dict[str, SalesOrder]:
    if not order_ids:
        return {}
    result = await session.execute(
        select(SalesOrder).where(SalesOrder.order_id.in_(order_ids))
    )
    return {row.order_id: row for row in result.scalars()}


def _format_from_chroma_metadata(meta: dict, comment: str) -> str:
    region = meta.get("region") or "未知区域"
    order_date = meta.get("order_date") or "未知日期"
    channel = meta.get("channel") or "未知渠道"
    product_category = meta.get("product_category") or "未知品类"
    sentiment = meta.get("sentiment") or "unknown"
    rating = int(meta.get("rating") or 0)
    return format_review_line(
        region=str(region),
        order_date=order_date,
        channel=str(channel),
        product_category=str(product_category),
        sentiment=str(sentiment),
        rating=rating,
        comment=comment,
    )


async def search_reviews_semantic(
    session: AsyncSession,
    user_query: str,
    top_k: int = 5,
) -> list[str]:
    """Chroma 语义检索，并补全/标注订单维度。"""
    embeddings = await embedding_model.embed_texts([user_query])
    collection = await get_comments_collection()

    def _query_sync():
        return collection.query(
            query_embeddings=embeddings,
            n_results=top_k,
            include=["documents", "metadatas"],
        )

    results = await asyncio.to_thread(_query_sync)
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return []

    missing_order_ids = [
        str(meta.get("order_id"))
        for meta in metas
        if meta and not meta.get("region") and meta.get("order_id")
    ]
    order_map = await _enrich_order_ids_from_mysql(session, missing_order_ids)

    formatted: list[str] = []
    for doc, meta in zip(docs, metas):
        if not doc:
            continue
        meta = meta or {}
        if meta.get("region"):
            formatted.append(_format_from_chroma_metadata(meta, doc))
            continue
        order_id = str(meta.get("order_id") or "")
        order = order_map.get(order_id)
        if order:
            formatted.append(
                format_review_line(
                    region=order.region,
                    order_date=order.order_date,
                    channel=order.channel,
                    product_category=order.product_category,
                    sentiment=str(meta.get("sentiment") or "unknown"),
                    rating=int(meta.get("rating") or 0),
                    comment=doc,
                )
            )
        else:
            formatted.append(
                f"[{meta.get('sentiment', 'unknown')}|{meta.get('rating', '?')}星] {doc}"
            )
    return formatted


async def fetch_reviews_for_agent(
    session: AsyncSession,
    user_query: str,
    sql_filters: list[dict],
    *,
    has_sql_context: bool,
    analysis_time_scope: str = "",
    top_k: int = 5,
) -> tuple[list[str], str]:
    """有 SQL 上下文时优先 MySQL 条件拉取；否则 Chroma 语义检索。"""
    if has_sql_context:
        reviews = await fetch_reviews_from_mysql(session, sql_filters, top_k=top_k)
        scope = build_reviews_scope_note(sql_filters, analysis_time_scope)
        if reviews:
            return reviews, scope
        semantic = await search_reviews_semantic(session, user_query, top_k=top_k)
        if semantic:
            return semantic, "当前过滤条件下无匹配评论，以下为语义相近的参考评论（已尽量标注订单维度）。"
        return ["未找到相关评论"], "未找到与当前分析条件匹配的评论。"

    semantic = await search_reviews_semantic(session, user_query, top_k=top_k)
    if semantic:
        return semantic, "以下评论按语义相关性检索，已标注区域/日期/渠道/品类。"
    return ["未找到相关评论"], "未找到相关评论。"
