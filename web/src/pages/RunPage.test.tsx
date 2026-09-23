import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RunPage } from './RunPage';

afterEach(() => cleanup());

function renderPage(overrides: Partial<React.ComponentProps<typeof RunPage>> = {}) {
  return render(<RunPage goal="分析项目" projectPath="." maxFiles={100} requireReview running={false} submitLabel="开始执行" error={null} events={[]} latestTaskId="" latestStatus="idle" workflowName="默认流程" taskNeedsReview={false} reviewComment="" resumeSnapshots={[]} selectedEvent={null} toolCalls={[]} agentOutputs={[]} onGoalChange={vi.fn()} onProjectPathChange={vi.fn()} onMaxFilesChange={vi.fn()} onRequireReviewChange={vi.fn()} onSubmit={vi.fn((event) => event.preventDefault())} onReviewCommentChange={vi.fn()} onReview={vi.fn()} onReviewAction={vi.fn()} {...overrides} />);
}

describe('RunPage', () => {
  it('submits the task form and renders the shared empty timeline', () => {
    const onSubmit = vi.fn((event) => event.preventDefault());
    renderPage({ onSubmit });
    fireEvent.submit(screen.getByRole('button', { name: '开始执行' }).closest('form')!);
    expect(onSubmit).toHaveBeenCalledOnce();
    expect(screen.getByText('运行任务后，这里会显示完整执行事件。')).toBeTruthy();
  });

  it('keeps the form disabled and presents a safe error when running fails', () => {
    renderPage({ running: true, error: new Error('任务提交失败') });
    expect(screen.getByRole('button', { name: '执行中...' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('任务提交失败');
  });

  it('owns review, resume, event detail, and output interactions', () => {
    const onReview = vi.fn();
    const onReviewAction = vi.fn();
    renderPage({
      taskNeedsReview: true,
      reviewComment: '请确认',
      resumeSnapshots: [{ resumed_from: 'review', action: 'approved', status: 'completed', before_state: { goal: '分析项目' }, after_events: [] }],
      selectedEvent: { node: 'analyze', agent: 'reviewer', status: 'completed', content: '节点输出' },
      toolCalls: ['filesystem.list: completed'],
      agentOutputs: ['Reviewer: 节点输出'],
      onReview,
      onReviewAction,
    });
    fireEvent.click(screen.getByRole('button', { name: '通过' }));
    fireEvent.click(screen.getByRole('button', { name: '深入分析' }));
    expect(onReview).toHaveBeenCalledWith('approve');
    expect(onReviewAction).toHaveBeenCalledWith('rerun_analysis');
    expect(screen.getByText('恢复节点')).toBeTruthy();
    expect(screen.getByText('节点输出')).toBeTruthy();
    expect(screen.getByText('filesystem.list: completed')).toBeTruthy();
  });
});
