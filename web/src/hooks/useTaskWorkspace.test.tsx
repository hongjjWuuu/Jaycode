import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  listTasks: vi.fn(), getTaskDetail: vi.fn(), getTaskEvents: vi.fn(), reviewTask: vi.fn(),
  runTaskStream: vi.fn(), runCollaborationTaskStream: vi.fn(), applyReviewAction: vi.fn(),
  askTask: vi.fn(), listProjectFiles: vi.fn(),
}));

vi.mock('../services/tasks', () => mocks);
vi.mock('../services/projectFiles', () => ({ listProjectFiles: mocks.listProjectFiles }));

import { useTaskWorkspace } from './useTaskWorkspace';

beforeEach(() => {
  vi.resetAllMocks();
  mocks.listTasks.mockResolvedValue([{ task_id: 'task-1', goal: 'review', status: 'waiting_review' }]);
  mocks.getTaskEvents.mockResolvedValue([{ type: 'node', task_id: 'task-1', status: 'completed', content: 'done' }]);
  mocks.getTaskDetail.mockResolvedValue({
    task: { task_id: 'task-1', final_report: 'stored report' },
    artifacts: [{ artifact_type: 'workflow_resume', name: 'resume', content: { task_id: 'task-1', action: 'approve' } }],
  });
  mocks.reviewTask.mockResolvedValue({});
});

describe('useTaskWorkspace', () => {
  it('owns SSE lifecycle and projects a task result', async () => {
    mocks.runTaskStream.mockImplementation(async (_payload, onEvent) => {
      onEvent({ type: 'node', task_id: 'task-1', status: 'running', content: 'planning' });
      onEvent({ type: 'task_result', task_id: 'task-1', status: 'completed', final_report: 'result', risk_level: 'medium', next_actions: ['review'] });
    });
    const { result } = renderHook(() => useTaskWorkspace());

    await act(async () => {
      await result.current.runTask({ goal: 'review', project_path: '.', max_files: 10, require_human_review: true, execution_mode: 'agent', workflow_name: 'default', input_text: 'review', nodes: [], edges: [] });
    });

    expect(mocks.runTaskStream).toHaveBeenCalledOnce();
    expect(result.current.running).toBe(false);
    expect(result.current.selectedTaskId).toBe('task-1');
    expect(result.current.events).toHaveLength(1);
    expect(result.current.finalReport).toBe('result');
    expect(result.current.riskLevel).toBe('medium');
  });

  it('restores task presentation and resume snapshots after review', async () => {
    const { result } = renderHook(() => useTaskWorkspace());
    await act(async () => { await result.current.submitReview('task-1', 'approve', 'looks good'); });

    expect(mocks.reviewTask).toHaveBeenCalledWith('task-1', 'approve', 'looks good');
    expect(result.current.selectedTaskId).toBe('task-1');
    expect(result.current.finalReport).toBe('stored report');
    expect(result.current.resumeSnapshots).toEqual([{ task_id: 'task-1', action: 'approve' }]);
  });

  it('keeps the compatible run error when stream startup fails', async () => {
    mocks.runTaskStream.mockRejectedValueOnce(new Error('stream unavailable'));
    const { result } = renderHook(() => useTaskWorkspace());

    await act(async () => {
      await expect(result.current.runTask({ goal: 'review', project_path: '.', max_files: 10, require_human_review: true, execution_mode: 'agent', workflow_name: 'default', input_text: 'review', nodes: [], edges: [] })).rejects.toThrow('stream unavailable');
    });

    expect(result.current.running).toBe(false);
    expect(result.current.runError).toBe('stream unavailable');
  });
});
