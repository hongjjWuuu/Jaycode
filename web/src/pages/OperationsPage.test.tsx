import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OperationsPage } from './OperationsPage';

afterEach(() => vi.unstubAllGlobals());

describe('OperationsPage', () => {
  it('shows filtered alerts and opens an operational task', async () => {
    const onOpenTask = vi.fn();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      readiness: { database: true, supervisor: false }, supervisor: { status: 'stopped', active_workers: 0, worker_count: 1, restart_count: 0 }, task_counts: { queued: 1 },
      oldest_queued_task: { task_id: 'queued-1', status: 'queued' }, waiting_review: [], recent_failed: [],
      alerts: [{ code: 'STALE_QUEUE', severity: 'warning', message: '排队超时' }],
    }), { status: 200 })));
    render(<OperationsPage onOpenTask={onOpenTask} />);
    await screen.findByText('STALE_QUEUE');
    fireEvent.click(screen.getByText(/打开最早排队任务/));
    expect(onOpenTask).toHaveBeenCalledWith('queued-1');
  });

  it('renders a compatible request error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ error_code: 'FORBIDDEN', message: '管理员权限不足', request_id: 'req-ops' }), { status: 403 })));
    render(<OperationsPage onOpenTask={() => undefined} />);
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('管理员权限不足'));
  });
});
