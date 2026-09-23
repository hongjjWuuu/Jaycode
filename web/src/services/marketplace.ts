import type { MarketplaceCatalogItem, MarketplaceInstall, MarketplacePreview } from '../types';
import { requestJson } from './http';

const API_BASE = '';
const json = (body: unknown): RequestInit => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
});

export async function listMarketplaceCatalog(): Promise<MarketplaceCatalogItem[]> {
  const data = await requestJson<{ items?: MarketplaceCatalogItem[] }>(
    `${API_BASE}/api/v1/marketplace/catalog`, {}, 'Marketplace catalog failed',
  );
  return data.items ?? [];
}

export async function listMarketplaceInstalls(
  limit = 80,
  packageType = '',
): Promise<MarketplaceInstall[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (packageType) params.set('package_type', packageType);
  const data = await requestJson<{ installs?: MarketplaceInstall[] }>(
    `${API_BASE}/api/v1/marketplace/installs?${params}`, {}, 'Marketplace installs failed',
  );
  return data.installs ?? [];
}

export function previewMarketplacePackage(sourceUrl: string): Promise<MarketplacePreview> {
  return requestJson(
    `${API_BASE}/api/v1/marketplace/preview`, json({ source_url: sourceUrl }), 'Marketplace preview failed',
  );
}

export async function installMarketplacePackage(sourceUrl: string): Promise<MarketplaceInstall> {
  const data = await requestJson<{ install: MarketplaceInstall }>(
    `${API_BASE}/api/v1/marketplace/install`, json({ source_url: sourceUrl }), 'Marketplace install failed',
  );
  return data.install;
}

export async function uninstallMarketplacePackage(packageId: string): Promise<MarketplaceInstall> {
  const data = await requestJson<{ uninstall: MarketplaceInstall }>(
    `${API_BASE}/api/v1/marketplace/packages/${encodeURIComponent(packageId)}`, { method: 'DELETE' }, 'Marketplace uninstall failed',
  );
  return data.uninstall;
}
