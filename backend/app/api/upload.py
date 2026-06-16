import asyncio
import io

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import insert

from app.database import Review, SalesOrder, get_db
from app.database.chroma_client import add_comment_to_chroma, get_comments_collection

router = APIRouter(prefix="/upload")

SALES_COLUMNS = [
    "order_id",
    "customer_id",
    "region",
    "product_category",
    "order_date",
    "revenue",
    "quantity",
    "channel",
]

REVIEWS_COLUMNS = [
    "review_id",
    "order_id",
    "rating",
    "comment",
    "sentiment",
]

SALES_STRING_COLUMNS = [
    "order_id",
    "customer_id",
    "region",
    "product_category",
    "channel",
]

REVIEWS_STRING_COLUMNS = [
    "review_id",
    "order_id",
    "comment",
    "sentiment",
]

CHROMA_CONCURRENCY = 10
CHROMA_CHUNK_SIZE = 500


def validate_sales_columns(df: pd.DataFrame) -> None:
    missing = set(SALES_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"缺少列: {', '.join(sorted(missing))}")
    if df.empty:
        raise ValueError("CSV 文件无数据")


def validate_reviews_columns(df: pd.DataFrame) -> None:
    missing = set(REVIEWS_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"缺少列: {', '.join(sorted(missing))}")
    if df.empty:
        raise ValueError("CSV 文件无数据")


def clean_sales_data(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df[SALES_COLUMNS].copy()

    cleaned["revenue"] = pd.to_numeric(cleaned["revenue"], errors="coerce")
    cleaned = cleaned[cleaned["revenue"].notna()]

    cleaned["order_date"] = pd.to_datetime(cleaned["order_date"], errors="coerce")
    cleaned = cleaned[cleaned["order_date"].notna()]
    cleaned["order_date"] = cleaned["order_date"].dt.date

    cleaned["quantity"] = pd.to_numeric(cleaned["quantity"], errors="coerce")
    cleaned = cleaned[cleaned["quantity"].notna()]
    cleaned["quantity"] = cleaned["quantity"].astype(int)

    for col in SALES_STRING_COLUMNS:
        cleaned[col] = cleaned[col].astype(str).str.strip()

    cleaned = cleaned.drop_duplicates(subset=["order_id"], keep="first")
    cleaned = cleaned.replace({np.nan: None})
    return cleaned.reset_index(drop=True)


def clean_reviews_data(df: pd.DataFrame) -> pd.DataFrame:
    cleaned = df[REVIEWS_COLUMNS].copy()

    cleaned["rating"] = pd.to_numeric(cleaned["rating"], errors="coerce")
    cleaned = cleaned[cleaned["rating"].notna()]
    cleaned["rating"] = cleaned["rating"].astype(int)

    cleaned["comment"] = cleaned["comment"].astype("string").str.strip()
    cleaned = cleaned[cleaned["comment"].notna() & cleaned["comment"].ne("")]

    for col in ["review_id", "order_id", "sentiment"]:
        cleaned[col] = cleaned[col].astype(str).str.strip()

    cleaned = cleaned.drop_duplicates(subset=["review_id"], keep="first")
    cleaned = cleaned.replace({np.nan: None})
    return cleaned.reset_index(drop=True)


async def _read_csv(file: UploadFile) -> pd.DataFrame:
    content = await file.read()
    return await asyncio.to_thread(pd.read_csv, io.BytesIO(content))


async def _clear_comments_collection() -> None:
    collection = await get_comments_collection()
    result = await asyncio.to_thread(collection.get)
    ids = result.get("ids") or []
    if ids:
        await asyncio.to_thread(collection.delete, ids=ids)


async def _write_reviews_to_chroma(
    records: list[dict],
    order_map: dict[str, dict],
) -> int:
    semaphore = asyncio.Semaphore(CHROMA_CONCURRENCY)

    async def _add_one(record: dict) -> None:
        async with semaphore:
            order = order_map.get(str(record["order_id"]), {})
            order_date = order.get("order_date")
            if hasattr(order_date, "isoformat"):
                order_date = order_date.isoformat()
            await add_comment_to_chroma(
                review_id=str(record["review_id"]),
                order_id=str(record["order_id"]),
                comment=str(record["comment"]),
                rating=int(record["rating"]),
                sentiment=str(record["sentiment"]),
                region=str(order.get("region") or ""),
                order_date=str(order_date or ""),
                channel=str(order.get("channel") or ""),
                product_category=str(order.get("product_category") or ""),
            )

    total_written = 0
    for offset in range(0, len(records), CHROMA_CHUNK_SIZE):
        chunk = records[offset : offset + CHROMA_CHUNK_SIZE]
        results = await asyncio.gather(
            *[_add_one(record) for record in chunk],
            return_exceptions=True,
        )
        errors = [result for result in results if isinstance(result, Exception)]
        if errors:
            raise errors[0]
        total_written += len(chunk)
    return total_written


async def _replace_sales_orders(
    session: AsyncSession,
    records: list[dict],
) -> None:
    """全量覆盖销售订单：先清子表 reviews 与 Chroma 评论，再清父表 sales_orders，最后批量插入。"""
    async with session.begin():
        await session.execute(text("DELETE FROM reviews"))
        await session.flush()
        await _clear_comments_collection()
        await session.execute(text("DELETE FROM sales_orders"))
        if records:
            await session.execute(insert(SalesOrder).values(records))


@router.post("/sales")
async def upload_sales(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    try:
        df = await _read_csv(file)
        validate_sales_columns(df)
        cleaned = clean_sales_data(df)
        records = cleaned.to_dict(orient="records")

        await _replace_sales_orders(session, records)
        return {"inserted": len(records)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except IntegrityError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"数据库完整性约束冲突: {exc.orig}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=400, detail=f"数据库操作失败: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


async def _filter_reviews_by_valid_orders(
    df: pd.DataFrame,
    session: AsyncSession,
) -> tuple[pd.DataFrame, int]:
    upload_order_ids = (
        df["order_id"].dropna().astype(str).str.strip().unique().tolist()
    )

    if upload_order_ids:
        result = await session.execute(
            select(SalesOrder.order_id).where(
                SalesOrder.order_id.in_(upload_order_ids)
            )
        )
        valid_db_ids = {row[0] for row in result.fetchall()}
    else:
        valid_db_ids = set()

    order_id_normalized = df["order_id"].astype(str).str.strip()
    df_clean = df[order_id_normalized.isin(valid_db_ids)]
    skipped_rows = len(df) - len(df_clean)
    return df_clean, skipped_rows


@router.post("/reviews")
async def upload_reviews(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    try:
        df = await _read_csv(file)
        validate_reviews_columns(df)

        df_clean, skipped_rows = await _filter_reviews_by_valid_orders(df, session)
        cleaned = clean_reviews_data(df_clean)
        records = cleaned.to_dict(orient="records")

        await session.execute(delete(Review))
        await _clear_comments_collection()
        if records:
            stmt = insert(Review).values(records)
            await session.execute(stmt)

        order_map: dict[str, dict] = {}
        if records:
            order_ids = list({str(r["order_id"]) for r in records})
            order_rows = await session.execute(
                select(SalesOrder).where(SalesOrder.order_id.in_(order_ids))
            )
            for order in order_rows.scalars():
                order_map[order.order_id] = {
                    "region": order.region,
                    "order_date": order.order_date,
                    "channel": order.channel,
                    "product_category": order.product_category,
                }

        chroma_written = (
            await _write_reviews_to_chroma(records, order_map) if records else 0
        )
        await session.commit()
        return {
            "inserted": len(records),
            "chroma_written": chroma_written,
            "skipped_rows": skipped_rows,
        }
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
