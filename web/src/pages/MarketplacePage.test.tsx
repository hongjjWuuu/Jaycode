import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MarketplacePage } from './MarketplacePage';

afterEach(() => cleanup());

describe('MarketplacePage', () => {
  it('keeps catalog and preview content inside their page panels', () => {
    const { container } = render(
      <MarketplacePage catalog={[]} installs={[]} preview={null} lastInstall={null}
        onRefresh={vi.fn().mockResolvedValue(undefined)} onPreview={vi.fn().mockResolvedValue({})}
        onInstall={vi.fn().mockResolvedValue({})} onUninstall={vi.fn().mockResolvedValue({})}
        onOpenSkill={vi.fn()} onApproveAndTestSkill={vi.fn().mockResolvedValue(undefined)} onCreateSkillWorkflow={vi.fn().mockResolvedValue(undefined)} />,
    );
    expect(container.querySelector('.marketplace-catalog-panel .marketplace-card-list')).toBeTruthy();
    expect(container.querySelector('.marketplace-preview-panel')).toBeTruthy();
    expect(container.querySelector('.marketplace-history-panel .marketplace-install-list')).toBeTruthy();
  });

  it('keeps page-local source input and sends it to preview', async () => {
    const preview = vi.fn().mockResolvedValue({ manifest: {}, summary: {} });
    render(
      <MarketplacePage
        catalog={[]}
        installs={[]}
        preview={null}
        lastInstall={null}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onPreview={preview}
        onInstall={vi.fn().mockResolvedValue({})}
        onUninstall={vi.fn().mockResolvedValue({})}
        onOpenSkill={vi.fn()}
        onApproveAndTestSkill={vi.fn().mockResolvedValue(undefined)}
        onCreateSkillWorkflow={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    const source = screen.getByDisplayValue('builtin://security-governance-skill-pack');
    fireEvent.change(source, { target: { value: 'builtin://demo' } });
    fireEvent.click(screen.getByRole('button', { name: '预览插件' }));

    await waitFor(() => expect(preview).toHaveBeenCalledWith('builtin://demo'));
  });

  it('shows a page-visible error when installation fails', async () => {
    render(
      <MarketplacePage
        catalog={[]}
        installs={[]}
        preview={null}
        lastInstall={null}
        onRefresh={vi.fn().mockResolvedValue(undefined)}
        onPreview={vi.fn().mockResolvedValue({})}
        onInstall={vi.fn().mockRejectedValue(new Error('安装被拒绝'))}
        onUninstall={vi.fn().mockResolvedValue({})}
        onOpenSkill={vi.fn()}
        onApproveAndTestSkill={vi.fn().mockResolvedValue(undefined)}
        onCreateSkillWorkflow={vi.fn().mockResolvedValue(undefined)}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: '安装插件包' }));
    expect(await screen.findByText('安装被拒绝')).toBeTruthy();
  });
});
