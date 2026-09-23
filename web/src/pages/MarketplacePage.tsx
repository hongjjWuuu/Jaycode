import { Check, FileText, History, Puzzle, RefreshCw } from 'lucide-react';
import { useState } from 'react';

import { FieldHelp, PanelTitle } from '../components/DisplayPrimitives';
import type { MarketplaceCatalogItem, MarketplaceInstall, MarketplacePreview } from '../types';

type MarketplacePageProps = {
  catalog: MarketplaceCatalogItem[];
  installs: MarketplaceInstall[];
  preview: MarketplacePreview | null;
  lastInstall: MarketplaceInstall | null;
  onRefresh: () => Promise<void>;
  onPreview: (sourceUrl: string) => Promise<MarketplacePreview>;
  onInstall: (sourceUrl: string) => Promise<MarketplaceInstall>;
  onUninstall: (packageId: string) => Promise<MarketplaceInstall>;
  onOpenSkill: (skillCode: string) => void;
  onApproveAndTestSkill: (skillCode: string) => Promise<void>;
  onCreateSkillWorkflow: (skillCode: string) => Promise<void>;
};

export function MarketplacePage({
  catalog, installs, preview, lastInstall, onRefresh, onPreview, onInstall, onUninstall,
  onOpenSkill, onApproveAndTestSkill, onCreateSkillWorkflow,
}: MarketplacePageProps) {
  const [sourceUrl, setSourceUrl] = useState('builtin://security-governance-skill-pack');
  const [packageType, setPackageType] = useState('all');
  const [message, setMessage] = useState('');
  const filteredCatalog = packageType === 'all' ? catalog : catalog.filter((item) => item.package_type === packageType);
  const packageTypes = ['all', 'skill_pack', 'rag_pack', 'mcp_pack', 'benchmark_pack', 'workflow_pack', 'prompt_pack'];
  const latestInstallByPackage = new Map<string, MarketplaceInstall>();
  for (const install of installs) {
    if (!latestInstallByPackage.has(install.package_id)) latestInstallByPackage.set(install.package_id, install);
  }
  const installedPackages = Array.from(latestInstallByPackage.values());
  const isInstalled = (packageId: string) => latestInstallByPackage.get(packageId)?.status === 'installed';
  const installResultSkills = lastInstall ? marketplaceInstalledSkillCodes(lastInstall) : [];
  const installCounts = packageTypes.slice(1).map((type) => ({
    type,
    count: installedPackages.filter((item) => item.package_type === type && item.status === 'installed').length,
  }));

  async function runAction(label: string, action: () => Promise<unknown>) {
    setMessage('');
    try {
      await action();
      setMessage(`${label} completed.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `${label} failed`);
    }
  }

  return (
    <section className="page-grid marketplace-page">
      <div className="panel marketplace-source-panel">
        <PanelTitle icon={<Puzzle size={17} />} title="Plugin Marketplace" action={<button className="icon-button" onClick={onRefresh}><RefreshCw size={15} /></button>} />
        <div className="marketplace-kpis">
          <KpiCard label="catalog" value={String(catalog.length)} />
          <KpiCard label="installed" value={String(Array.from(latestInstallByPackage.values()).filter((item) => item.status === 'installed').length)} />
          <KpiCard label="failed" value={String(Array.from(latestInstallByPackage.values()).filter((item) => item.status === 'failed').length)} />
        </div>
        <form className="marketplace-form">
          <label>
            GitHub / URL / local path
            <input value={sourceUrl} onChange={(event) => setSourceUrl(event.target.value)} />
            <FieldHelp>支持 builtin://package-id、GitHub 仓库 URL、zip/json/SKILL.md URL、本地目录、本地 plugin.json。没有 plugin.json 但包含 SKILL.md 时，会自动转换成声明式 Skill 插件。</FieldHelp>
          </label>
          <div className="marketplace-actions">
            <button type="button" className="secondary" onClick={() => runAction('Preview', () => onPreview(sourceUrl))}>预览插件</button>
            <button type="button" className="primary" onClick={() => runAction('Install', () => onInstall(sourceUrl))}>安装插件包</button>
          </div>
        </form>
        {message ? <p className="marketplace-message">{message}</p> : null}
        <div className="marketplace-type-row">
          {installCounts.map((item) => <KpiCard key={item.type} label={marketplaceTypeLabel(item.type)} value={String(item.count)} />)}
        </div>
      </div>

      {lastInstall ? (
        <div className="panel marketplace-result-panel">
          <PanelTitle icon={<Check size={17} />} title="最近安装结果" />
          <div className={`marketplace-install-result ${lastInstall.status}`}>
            <strong>{lastInstall.name}</strong>
            <span>{lastInstall.package_type} / {lastInstall.status} / {marketplaceResourceCount(lastInstall)} resources</span>
            {lastInstall.status === 'installed' && installResultSkills.length ? (
              <div className="marketplace-skill-actions">
                <p>已安装 {installResultSkills.length} 个 Skill</p>
                {installResultSkills.map((skillCode) => (
                  <article key={skillCode}>
                    <span>{marketplaceSkillName(lastInstall, skillCode)}</span>
                    <code>{skillCode}</code>
                    <div className="marketplace-actions">
                      <button type="button" className="secondary" onClick={() => onOpenSkill(skillCode)}>去 Skills 查看</button>
                      <button type="button" className="secondary" onClick={() => runAction('Approve and test', () => onApproveAndTestSkill(skillCode))}>审批手动测试</button>
                      <button type="button" className="primary" onClick={() => runAction('Create Workflow', () => onCreateSkillWorkflow(skillCode))}>添加到 Workflow</button>
                    </div>
                    <small>严格模式：审批手动测试只会放行 skill_console；添加到 Workflow 只创建节点，不会自动放行。Workflow 运行前必须手动审批 workflow_runner。</small>
                  </article>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="panel marketplace-catalog-panel">
        <PanelTitle icon={<Puzzle size={17} />} title="资源包目录" />
        <div className="marketplace-tabs">
          {packageTypes.map((type) => <button key={type} className={packageType === type ? 'active' : ''} onClick={() => setPackageType(type)}>{marketplaceTypeLabel(type)}</button>)}
        </div>
        <div className="marketplace-card-list">
          {filteredCatalog.map((item) => (
            <article key={item.package_id} className="marketplace-card">
              <div><strong>{item.name}</strong><span>{item.package_id} / {item.version}</span></div>
              <p>{item.description}</p>
              <div className="skill-tags">
                <span>{marketplaceTypeLabel(item.package_type)}</span>
                {isInstalled(item.package_id) ? <span className="installed">installed</span> : <span>not installed</span>}
                {item.permissions.map((permission) => <span key={permission}>{permission}</span>)}
              </div>
              <div className="marketplace-actions">
                <button className="secondary" onClick={() => setSourceUrl(item.source_url)}>填入 URL</button>
                <button className="secondary" onClick={() => runAction('Preview', () => onPreview(item.source_url))}>预览</button>
                <button className="primary" onClick={() => runAction('Install', () => onInstall(item.source_url))}>{isInstalled(item.package_id) ? '重新安装' : '安装'}</button>
                <button className="secondary danger" disabled={!isInstalled(item.package_id)} onClick={() => runAction('Uninstall', () => onUninstall(item.package_id))}>卸载</button>
              </div>
            </article>
          ))}
          {!filteredCatalog.length ? <p className="empty-text">暂无该类型资源包。</p> : null}
        </div>
      </div>

      <div className="panel marketplace-preview-panel">
        <PanelTitle icon={<FileText size={17} />} title="预览 / 权限" />
        {preview ? (
          <div className="marketplace-preview">
            <div className="marketplace-summary-grid">
              {Object.entries(preview.summary).map(([key, value]) => <KpiCard key={key} label={key} value={Array.isArray(value) ? String(value.length) : String(value)} />)}
            </div>
            <details className="skill-json" open><summary>manifest / plugin.json / SKILL.md</summary><pre>{JSON.stringify(preview.manifest, null, 2)}</pre></details>
          </div>
        ) : <p className="empty-text">先选择资源包或输入 URL 进行预览。</p>}
      </div>

      <div className="panel marketplace-history-panel">
        <PanelTitle icon={<History size={17} />} title="安装历史" />
        <div className="marketplace-install-list">
          {installs.map((install) => (
            <article key={install.install_id} className={`marketplace-install ${install.status}`}>
              <div><strong>{install.name}</strong><span>{install.package_type} / {install.version || '-'} / {install.installed_at}</span></div>
              <p>{install.source_url}</p>
              {install.error_message ? <p className="error-text">{install.error_message}</p> : null}
              <details className="skill-json"><summary>安装摘要</summary><pre>{JSON.stringify({ summary: install.summary, manifest: install.manifest }, null, 2)}</pre></details>
            </article>
          ))}
          {!installs.length ? <p className="empty-text">暂无安装历史。</p> : null}
        </div>
      </div>
    </section>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) {
  return <div className="kpi-card"><span>{label}</span><strong>{value}</strong></div>;
}

function marketplaceTypeLabel(type: string) {
  const labels: Record<string, string> = { all: 'All', skill_pack: 'Skill', rag_pack: 'RAG', mcp_pack: 'MCP', benchmark_pack: 'Benchmark', workflow_pack: 'Workflow', prompt_pack: 'Prompt' };
  return labels[type] ?? type;
}

function marketplaceInstalledSkillCodes(install: MarketplaceInstall) {
  const summarySkills = install.summary?.installed_skills;
  if (Array.isArray(summarySkills)) return summarySkills.map(String);
  const manifestSkills = install.manifest?.skills;
  if (!Array.isArray(manifestSkills)) return [];
  return manifestSkills.map((skill) => (skill && typeof skill === 'object' ? String((skill as Record<string, unknown>).code ?? '') : '')).filter(Boolean);
}

function marketplaceSkillName(install: MarketplaceInstall, skillCode: string) {
  const manifestSkills = install.manifest?.skills;
  if (Array.isArray(manifestSkills)) {
    const match = manifestSkills.find((skill) => skill && typeof skill === 'object' && String((skill as Record<string, unknown>).code ?? '') === skillCode);
    if (match && typeof match === 'object') return String((match as Record<string, unknown>).name ?? skillCode);
  }
  return skillCode;
}

function marketplaceResourceCount(install: MarketplaceInstall) {
  const keys = ['installed_skills', 'saved_notes', 'registered_servers', 'installed_workflows', 'installed_prompts', 'benchmark_cases'];
  const total = keys.reduce((sum, key) => sum + (Array.isArray(install.summary?.[key]) ? install.summary[key].length : 0), 0);
  return total || marketplaceInstalledSkillCodes(install).length;
}
