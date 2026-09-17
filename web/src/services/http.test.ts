import { describe, expect, it, vi } from 'vitest';
import { consumeSse } from './http';

describe('consumeSse', () => {
  it('parses JSON data frames split across stream chunks', async () => {
    const encoder = new TextEncoder();
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(encoder.encode('data: {"kind":"queued"'));
        controller.enqueue(encoder.encode('}\n\ndata: {"kind":"done"}\n\n'));
        controller.close();
      },
    });
    const onData = vi.fn();

    await consumeSse(new Response(stream), onData);

    expect(onData).toHaveBeenNthCalledWith(1, { kind: 'queued' });
    expect(onData).toHaveBeenNthCalledWith(2, { kind: 'done' });
  });
});
