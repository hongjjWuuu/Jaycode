import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BenchmarkPage } from './BenchmarkPage';

afterEach(() => cleanup());
function renderPage(overrides: Partial<React.ComponentProps<typeof BenchmarkPage>> = {}) {
  return render(<BenchmarkPage benchmarkType="mcp" runs={[]} selectedRun={null} running={false} error=""
    onBenchmarkTypeChange={vi.fn().mockResolvedValue(undefined)} onRun={vi.fn().mockResolvedValue({ run_id: 'run-1' })}
    onOpen={vi.fn().mockResolvedValue(undefined)} onRefresh={vi.fn().mockResolvedValue(undefined)} {...overrides} />);
}

describe('BenchmarkPage', () => {
  it('submits the selected benchmark payload through the Hook callback', async () => {
    const onRun = vi.fn().mockResolvedValue({ run_id: 'run-1' });
    renderPage({ onRun });
    fireEvent.submit(screen.getByRole('button', { name: 'Run MCP Benchmark' }).closest('form')!);
    expect(onRun).toHaveBeenCalledWith(expect.objectContaining({ agent_code: 'benchmark_runner', iterations: 3 }));
  });

  it('shows a failed benchmark operation without leaving the page busy', async () => {
    renderPage({ onRun: vi.fn().mockRejectedValue(new Error('MCP benchmark failed')) });
    fireEvent.submit(screen.getByRole('button', { name: 'Run MCP Benchmark' }).closest('form')!);
    expect(await screen.findByText('MCP benchmark failed')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Run MCP Benchmark' })).not.toBeDisabled();
  });
});
