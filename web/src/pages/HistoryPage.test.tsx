import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HistoryPage } from './HistoryPage';

afterEach(() => cleanup());

describe('HistoryPage', () => {
  it('opens a selected task and refreshes history', () => {
    const onOpen = vi.fn(); const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<HistoryPage tasks={[{ task_id: 'task-1', goal: '历史任务', status: 'completed', created_at: '', updated_at: '' }]} deletedTasks={[]} taskActor={null} selectedTaskId="" events={[]} finalReport="" onOpen={onOpen} onRefresh={onRefresh} onRefreshDeleted={vi.fn()} onDelete={vi.fn()} onRestore={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: /历史任务/ }));
    fireEvent.click(document.querySelector('.history-list-panel .icon-button')!);
    expect(onOpen).toHaveBeenCalledWith('task-1');
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(screen.getByText('选择历史任务后，这里会显示完整执行事件。')).toBeTruthy();
  });

  it('shows a compatible API error when history refresh fails', async () => {
    render(<HistoryPage tasks={[]} deletedTasks={[]} taskActor={null} selectedTaskId="" events={[]} finalReport="" onOpen={vi.fn()} onRefresh={vi.fn().mockRejectedValue({ message: '历史加载失败', error_code: 'dependency_unavailable', request_id: 'req-history-1' })} onRefreshDeleted={vi.fn()} onDelete={vi.fn()} onRestore={vi.fn()} />);
    fireEvent.click(document.querySelector('.history-list-panel .icon-button')!);
    expect(await screen.findByRole('alert')).toHaveTextContent('历史加载失败');
  });

  it('moves selected terminal tasks to the recycle bin', async () => {
    const onDelete = vi.fn().mockResolvedValue({ deleted: [{ task_id: 'task-1' }], restored: [], skipped: [], failed: [] });
    vi.stubGlobal('confirm', vi.fn(() => true));
    render(<HistoryPage tasks={[{ task_id: 'task-1', goal: '可删除任务', status: 'completed', created_at: '', updated_at: '' }, { task_id: 'task-2', goal: '运行中任务', status: 'running', created_at: '', updated_at: '' }]} deletedTasks={[]} taskActor={null} selectedTaskId="" events={[]} finalReport="" onOpen={vi.fn()} onRefresh={vi.fn()} onRefreshDeleted={vi.fn()} onDelete={onDelete} onRestore={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: '选择删除' }));
    fireEvent.click(screen.getByLabelText('选择 可删除任务'));
    expect(screen.getByLabelText('选择 运行中任务')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: /删除所选/ }));
    expect(onDelete).toHaveBeenCalledWith(['task-1']);
    expect(await screen.findByText(/已移入回收站 1 项/)).toBeTruthy();
  });
});
