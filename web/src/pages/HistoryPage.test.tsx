import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { HistoryPage } from './HistoryPage';

afterEach(() => cleanup());

describe('HistoryPage', () => {
  it('opens a selected task and refreshes history', () => {
    const onOpen = vi.fn(); const onRefresh = vi.fn().mockResolvedValue(undefined);
    render(<HistoryPage tasks={[{ task_id: 'task-1', goal: '历史任务', status: 'completed', created_at: '', updated_at: '' }]} selectedTaskId="" events={[]} finalReport="" onOpen={onOpen} onRefresh={onRefresh} />);
    fireEvent.click(screen.getByRole('button', { name: /历史任务/ }));
    fireEvent.click(document.querySelector('.history-list-panel .icon-button')!);
    expect(onOpen).toHaveBeenCalledWith('task-1');
    expect(onRefresh).toHaveBeenCalledOnce();
    expect(screen.getByText('选择历史任务后，这里会显示完整执行事件。')).toBeTruthy();
  });
});
