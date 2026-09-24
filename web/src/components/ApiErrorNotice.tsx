import { useState } from 'react';
import { ApiError } from '../services/http';

/** Presents the compatible API error envelope without exposing implementation detail. */
export function ApiErrorNotice({ error, fallback = '请求失败，请稍后重试。' }: { error: unknown; fallback?: string }) {
  const [copied, setCopied] = useState(false);
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const envelope = !apiError && isErrorEnvelope(error) ? error : null;
  const message = apiError?.message || envelope?.message || (error instanceof Error ? error.message : typeof error === 'string' ? error : fallback);
  const errorCode = apiError?.errorCode ?? envelope?.error_code;
  const requestId = apiError?.requestId ?? envelope?.request_id;
  const copyRequestId = async () => {
    if (!requestId || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(requestId);
    setCopied(true);
  };
  return <div className="error-text" role="alert">
    <p>{message}</p>
    {errorCode ? <small>错误码：{errorCode}</small> : null}
    {requestId ? <button type="button" className="secondary" onClick={() => void copyRequestId()}>{copied ? '已复制 request_id' : `复制 request_id: ${requestId}`}</button> : null}
  </div>;
}

type ErrorEnvelope = { message: string; error_code?: string; request_id?: string };

function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return typeof data.message === 'string';
}
