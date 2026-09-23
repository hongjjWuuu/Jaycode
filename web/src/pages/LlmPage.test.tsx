import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LlmPage } from './LlmPage';

afterEach(() => cleanup());

const prompt = { agent: 'planner', prompt_family: 'planner', prompt_version: 'planner.v1', title: 'Planner', description: '', system_suffix: '', is_active: false, created_at: '', updated_at: '' };
function renderPage(overrides: Partial<React.ComponentProps<typeof LlmPage>> = {}) {
  return render(<LlmPage prompts={[prompt]} usage={null} traces={[]} traceAgent="" agentFilter=""
    onAgentFilterChange={vi.fn().mockResolvedValue(undefined)} onTraceAgentChange={vi.fn().mockResolvedValue(undefined)}
    onActivatePrompt={vi.fn().mockResolvedValue(undefined)} onSavePrompt={vi.fn().mockResolvedValue(undefined)}
    onRunAbTest={vi.fn().mockResolvedValue({ comparison: { winner: 'A', criteria: [] }, prompt_a: {}, prompt_b: {} })}
    onRefresh={vi.fn().mockResolvedValue(undefined)} {...overrides} />);
}

describe('LlmPage', () => {
  it('activates a prompt through its explicit governance callback', async () => {
    const onActivatePrompt = vi.fn().mockResolvedValue(undefined);
    renderPage({ onActivatePrompt });
    fireEvent.click(screen.getByRole('button', { name: '设为 active' }));
    expect(onActivatePrompt).toHaveBeenCalledWith(prompt);
  });

  it('shows a prompt save error from the compatible error message', async () => {
    renderPage({ onSavePrompt: vi.fn().mockRejectedValue(new Error('invalid prompt [request_id=req-1]')) });
    fireEvent.submit(screen.getByRole('button', { name: '保存 Prompt' }).closest('form')!);
    expect(await screen.findByText('invalid prompt [request_id=req-1]')).toBeTruthy();
  });
});
