import { describe, expect, it, vi } from 'vitest';
import { getOperationsOverview } from './operations';

describe('operations service', () => {
  it('reads the bounded overview endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ task_counts: {} }), { status: 200 })));
    await expect(getOperationsOverview()).resolves.toMatchObject({ task_counts: {} });
    expect(fetch).toHaveBeenCalledWith('/api/v1/operations/overview', {});
  });

  it('keeps the compatible API error envelope', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error_code: 'FORBIDDEN', message: '管理员权限不足', request_id: 'req-ops' }), { status: 403 })));
    await expect(getOperationsOverview()).rejects.toMatchObject({ errorCode: 'FORBIDDEN', requestId: 'req-ops' });
  });
});
