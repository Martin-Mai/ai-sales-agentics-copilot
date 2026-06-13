import asyncio
import io

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import insert

from app.database import Review, SalesOrder, get_db
from app.database.chroma_client import add_comment_to_chroma

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


async def _write_reviews_to_chroma(records: list[dict]) -> int:
    semaphore = asyncio.Semaphore(CHROMA_CONCURRENCY)

    async def _add_one(record: dict) -> None:
        async with semaphore:
            await add_comment_to_chroma(
                review_id=str(record["review_id"]),
                order_id=str(record["order_id"]),
                comment=str(record["comment"]),
                rating=int(record["rating"]),
                sentiment=str(record["sentiment"]),
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

        await session.execute(delete(SalesOrder))
        if records:
            stmt = insert(SalesOrder).values(records)
            await session.execute(stmt)
        await session.commit()
        return {"inserted": len(records)}
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await session.rollback()
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
        if records:
            stmt = insert(Review).values(records)
            await session.execute(stmt)

        chroma_written = await _write_reviews_to_chroma(records) if records else 0
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
