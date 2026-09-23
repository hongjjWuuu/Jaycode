import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiErrorNotice } from './ApiErrorNotice';
import { ApiError } from '../services/http';

afterEach(() => cleanup());

describe('ApiErrorNotice', () => {
  it('renders the stable envelope fields and copies request_id', async () => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
    render(<ApiErrorNotice error={new ApiError('WORKFLOW_INVALID', 'req-42', '流程定义无效')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('流程定义无效');
    expect(screen.getByText('错误码：WORKFLOW_INVALID')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '复制 request_id: req-42' }));
    expect(await screen.findByText('已复制 request_id')).toBeTruthy();
  });

  it('keeps a safe fallback for non-envelope failures', () => {
    render(<ApiErrorNotice error={new Error('暂时不可用')} />);
    expect(screen.getByRole('alert')).toHaveTextContent('暂时不可用');
  });
});
