export class ApiError extends Error {
  constructor(public readonly errorCode: string, public readonly requestId: string | undefined, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

/** Converts both the P2 envelope and legacy detail errors into one client error type. */
export async function responseError(response: Response, fallback: string): Promise<ApiError> {
  const data = await response.json().catch(() => ({})) as Record<string, unknown>;
  return new ApiError(
    String(data.error_code ?? `HTTP_${response.status}`),
    typeof data.request_id === 'string' ? data.request_id : undefined,
    String(data.message ?? data.detail ?? `${fallback}: ${response.status}`),
  );
}

export async function requestJson<T>(path: string, init: RequestInit = {}, fallback = 'Request failed'): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) throw await responseError(response, fallback);
  return response.json() as Promise<T>;
}

/** Parses complete Server-Sent Event frames while preserving the API's event payload contract. */
export async function consumeSse<T = unknown>(response: Response, onData: (data: T) => void): Promise<void> {
  if (!response.body) throw new Error('SSE response body is unavailable');
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split('\n\n');
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const dataLine = frame.split('\n').find((line) => line.startsWith('data: '));
      if (dataLine) onData(JSON.parse(dataLine.slice(6).trim()) as T);
    }
  }
}
