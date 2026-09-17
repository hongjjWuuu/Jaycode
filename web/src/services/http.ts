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
