import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiError } from './http';
import {
  installMarketplacePackage,
  listMarketplaceInstalls,
  previewMarketplacePackage,
} from './marketplace';

afterEach(() => vi.restoreAllMocks());

describe('Marketplace service', () => {
  it('encodes install filters and unwraps installation records', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ installs: [{ package_id: 'demo', status: 'installed' }] }), { status: 200 }),
    );

    await expect(listMarketplaceInstalls(25, 'skill pack')).resolves.toEqual([
      { package_id: 'demo', status: 'installed' },
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/marketplace/installs?limit=25&package_type=skill+pack', {},
    );
  });

  it('sends the source URL for preview and installation', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify({ manifest: {}, summary: {} }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ install: { package_id: 'demo', status: 'installed' } }), { status: 200 }));

    await expect(previewMarketplacePackage('https://example.test/demo.zip')).resolves.toMatchObject({ summary: {} });
    await expect(installMarketplacePackage('https://example.test/demo.zip')).resolves.toMatchObject({ package_id: 'demo' });
    expect(fetchMock).toHaveBeenNthCalledWith(1, '/api/v1/marketplace/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_url: 'https://example.test/demo.zip' }),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/api/v1/marketplace/install', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ source_url: 'https://example.test/demo.zip' }),
    });
  });

  it('exposes a compatible error envelope for an invalid preview source', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error_code: 'MARKETPLACE_SOURCE_INVALID', message: 'Source is not trusted.', request_id: 'req-market-1' }), { status: 400 }),
    );

    await expect(previewMarketplacePackage('http://example.test/demo.zip'))
      .rejects.toEqual(new ApiError('MARKETPLACE_SOURCE_INVALID', 'req-market-1', 'Source is not trusted.'));
  });
});
