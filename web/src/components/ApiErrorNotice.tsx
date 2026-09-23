import { useState } from 'react';
import { ApiError } from '../services/http';

/** Presents the compatible API error envelope without exposing implementation detail. */
export function ApiErrorNotice({ error, fallback = '请求失败，请稍后重试。' }: { error: unknown; fallback?: string }) {
  const [copied, setCopied] = useState(false);
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const message = apiError?.message || (error instanceof Error ? error.message : typeof error === 'string' ? error : fallback);
  const copyRequestId = async () => {
    if (!apiError?.requestId || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(apiError.requestId);
    setCopied(true);
  };
  return <div className="error-text" role="alert">
    <p>{message}</p>
    {apiError ? <small>错误码：{apiError.errorCode}</small> : null}
    {apiError?.requestId ? <button type="button" className="secondary" onClick={() => void copyRequestId()}>{copied ? '已复制 request_id' : `复制 request_id: ${apiError.requestId}`}</button> : null}
  </div>;
}
