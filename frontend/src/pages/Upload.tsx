import { useCallback, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowLeft,
  CheckCircle2,
  FileSpreadsheet,
  Loader2,
  UploadCloud,
  XCircle,
} from 'lucide-react';
import { uploadReviews, uploadSales } from '../services/api';
import type { UploadReviewsResponse, UploadSalesResponse } from '../types';

type UploadKind = 'sales' | 'reviews';

interface FileSlot {
  kind: UploadKind;
  label: string;
  filename: string;
  description: string;
  file: File | null;
  status: 'idle' | 'uploading' | 'success' | 'error';
  result?: UploadSalesResponse | UploadReviewsResponse;
  error?: string;
}

const INITIAL_SLOTS: FileSlot[] = [
  {
    kind: 'sales',
    label: '销售数据',
    filename: 'sales_data.csv',
    description: '订单、区域、品类、营收等销售明细',
    file: null,
    status: 'idle',
  },
  {
    kind: 'reviews',
    label: '评论数据',
    filename: 'reviews_data.csv',
    description: '用户评分、评论内容、情感标签',
    file: null,
    status: 'idle',
  },
];

function DropZone({
  slot,
  onFile,
}: {
  slot: FileSlot;
  onFile: (kind: UploadKind, file: File) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) onFile(slot.kind, file);
    },
    [onFile, slot.kind],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
      className={`relative rounded-2xl border-2 border-dashed p-8 text-center transition ${
        dragOver
          ? 'border-brand-400 bg-brand-50 dark:border-brand-500 dark:bg-brand-500/10'
          : 'border-slate-200 bg-white dark:border-slate-600 dark:bg-slate-800/50'
      }`}
    >
      <input
        type="file"
        accept=".csv"
        className="absolute inset-0 cursor-pointer opacity-0"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(slot.kind, file);
        }}
      />

      <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-500 dark:bg-brand-500/15">
        {slot.status === 'uploading' ? (
          <Loader2 className="h-7 w-7 animate-spin" />
        ) : (
          <UploadCloud className="h-7 w-7" />
        )}
      </div>

      <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
        {slot.label}
      </h3>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
        {slot.description}
      </p>
      <p className="mt-3 text-sm text-brand-600 dark:text-brand-400">
        拖拽 <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs dark:bg-slate-700">{slot.filename}</code> 到此处，或点击选择文件
      </p>

      {slot.file && (
        <div className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-100 px-3 py-1.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
          <FileSpreadsheet className="h-3.5 w-3.5" />
          {slot.file.name} ({(slot.file.size / 1024).toFixed(1)} KB)
        </div>
      )}

      {slot.status === 'success' && slot.result && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm text-green-600 dark:text-green-400">
          <CheckCircle2 className="h-4 w-4" />
          成功导入 {slot.result.inserted} 行
          {'skipped_rows' in slot.result && slot.result.skipped_rows > 0 && (
            <span className="text-slate-500">
              （跳过 {slot.result.skipped_rows} 行无效订单）
            </span>
          )}
          {'chroma_written' in slot.result && (
            <span className="text-slate-500">
              · 向量索引 {slot.result.chroma_written} 条
            </span>
          )}
        </div>
      )}

      {slot.status === 'error' && (
        <div className="mt-4 flex items-center justify-center gap-2 text-sm text-red-500">
          <XCircle className="h-4 w-4" />
          {slot.error ?? '上传失败'}
        </div>
      )}
    </div>
  );
}

export default function Upload() {
  const [slots, setSlots] = useState<FileSlot[]>(INITIAL_SLOTS);

  const handleFile = async (kind: UploadKind, file: File) => {
    setSlots((prev) =>
      prev.map((s) =>
        s.kind === kind
          ? { ...s, file, status: 'uploading', error: undefined, result: undefined }
          : s,
      ),
    );

    try {
      const result =
        kind === 'sales' ? await uploadSales(file) : await uploadReviews(file);
      setSlots((prev) =>
        prev.map((s) =>
          s.kind === kind ? { ...s, status: 'success', result } : s,
        ),
      );
    } catch (err) {
      const message =
        err instanceof Error ? err.message : '上传失败，请稍后重试';
      setSlots((prev) =>
        prev.map((s) =>
          s.kind === kind ? { ...s, status: 'error', error: message } : s,
        ),
      );
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-white to-brand-50/30 dark:from-slate-900 dark:via-slate-900 dark:to-indigo-950/30">
      <div className="mx-auto max-w-4xl px-6 py-10">
        <Link
          to="/chat"
          className="mb-8 inline-flex items-center gap-2 text-sm text-slate-500 transition hover:text-brand-600 dark:text-slate-400 dark:hover:text-brand-400"
        >
          <ArrowLeft className="h-4 w-4" />
          返回聊天
        </Link>

        <header className="mb-10">
          <h1 className="text-3xl font-bold text-slate-800 dark:text-slate-100">
            数据源上传
          </h1>
          <p className="mt-2 text-slate-500 dark:text-slate-400">
            上传 CSV 文件以初始化销售数据库与评论向量索引，供 AI 助理分析使用。
          </p>
        </header>

        <div className="grid gap-6 md:grid-cols-2">
          {slots.map((slot) => (
            <DropZone key={slot.kind} slot={slot} onFile={handleFile} />
          ))}
        </div>

        <div className="mt-8 rounded-xl border border-slate-200 bg-white/80 p-5 text-sm text-slate-600 dark:border-slate-700 dark:bg-slate-800/50 dark:text-slate-400">
          <h4 className="mb-2 font-medium text-slate-800 dark:text-slate-200">
            文件格式要求
          </h4>
          <ul className="list-inside list-disc space-y-1 text-xs">
            <li>
              <strong>sales_data.csv</strong>：order_id, customer_id, region,
              product_category, order_date, revenue, quantity, channel
            </li>
            <li>
              <strong>reviews_data.csv</strong>：review_id, order_id, rating,
              comment, sentiment
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
