import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { McpPage } from './McpPage';

afterEach(() => cleanup());

function renderPage(overrides: Partial<React.ComponentProps<typeof McpPage>> = {}) {
  return render(<McpPage
    projectPath="."
    status={null}
    servers={[]}
    tools={[]}
    logs={[]}
    onRefresh={vi.fn().mockResolvedValue(undefined)}
    onSaveServer={vi.fn().mockResolvedValue(undefined)}
    onServerEnabled={vi.fn().mockResolvedValue(undefined)}
    onDiscover={vi.fn().mockResolvedValue(undefined)}
    onToolEnabled={vi.fn().mockResolvedValue(undefined)}
    onApproveTool={vi.fn().mockResolvedValue(undefined)}
    onCallTool={vi.fn().mockResolvedValue({})}
    {...overrides}
  />);
}

describe('McpPage', () => {
  it('sends a parsed Server draft through the explicit callback', async () => {
    const onSaveServer = vi.fn().mockResolvedValue(undefined);
    renderPage({ onSaveServer });

    fireEvent.submit(screen.getByRole('button', { name: '保存 Server' }).closest('form')!);

    await waitFor(() => expect(onSaveServer).toHaveBeenCalledWith(expect.objectContaining({
      server_id: 'real_filesystem', args: ['scripts/launch_mcp_filesystem.py', '.'], env: {},
    })));
  });

  it('shows a visible error when saving a Server fails', async () => {
    renderPage({ onSaveServer: vi.fn().mockRejectedValue(new Error('命令不在白名单中')) });

    fireEvent.submit(screen.getByRole('button', { name: '保存 Server' }).closest('form')!);
    expect(await screen.findByText('命令不在白名单中')).toBeTruthy();
  });
});
