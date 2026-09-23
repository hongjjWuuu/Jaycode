import { FileText, History, Play, Puzzle, RefreshCw, ShieldCheck } from 'lucide-react';
import { FormEvent, useEffect, useState } from 'react';

import { EnabledState, FieldHelp, PanelTitle, RiskBadge } from '../components/DisplayPrimitives';
import { listSkillVersions, rollbackSkillVersion, testSkill } from '../services/skills';
import type { SkillApproval, SkillExecutionLog, SkillPlugin, SkillRecord, SkillTestResult, SkillVersionSnapshot } from '../types';

type SkillsPageProps = {
  plugins: SkillPlugin[];
  skills: SkillRecord[];
  approvals: SkillApproval[];
  logs: SkillExecutionLog[];
  selectedSkillCode: string;
  projectPath: string;
  onSelectSkill: (code: string) => void;
  onRefresh: () => Promise<void>;
  onSkillEnabled: (skillCode: string, enabled: boolean) => Promise<void>;
  onSkillApproval: (skillCode: string, agentCode: string, allowed: boolean, reason: string) => Promise<void>;
  onExecuteSkill: (skillCode: string, agentCode: string, input: Record<string, unknown>) => Promise<{ output: Record<string, unknown>; log_id: string; status: string; latency_ms: number }>;
  onAddToWorkflow: (skill: SkillRecord) => void;
  onUninstallPlugin: (pluginId: string) => Promise<Record<string, unknown>>;
};

export function SkillsPage({
  plugins, skills, approvals, logs, selectedSkillCode, projectPath, onSelectSkill, onRefresh,
  onSkillEnabled, onSkillApproval, onExecuteSkill, onAddToWorkflow, onUninstallPlugin,
}: SkillsPageProps) {
  const selectedSkill = skills.find((item) => item.code === selectedSkillCode) ?? skills[0] ?? null;
  const [agentCode, setAgentCode] = useState('skill_console');
  const [approvalReason, setApprovalReason] = useState('Approved from Skills console.');
  const [inputText, setInputText] = useState('{}');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [versions, setVersions] = useState<SkillVersionSnapshot[]>([]);
  const [testResult, setTestResult] = useState<SkillTestResult | null>(null);
  const categories = Array.from(new Set(skills.map((skill) => skill.category))).sort();
  const filteredSkills = categoryFilter === 'all' ? skills : skills.filter((skill) => skill.category === categoryFilter);
  const activeApproval = selectedSkill ? approvals.find((item) => item.skill_code === selectedSkill.code && item.agent_code === agentCode) : undefined;
  const activePlugin = selectedSkill ? plugins.find((plugin) => plugin.plugin_id === selectedSkill.plugin_id) : null;
  const selectedSkillApprovals = selectedSkill ? approvals.filter((approval) => approval.skill_code === selectedSkill.code) : [];

  useEffect(() => {
    if (!selectedSkill) return;
    const nextInput = { ...(selectedSkill.default_input ?? {}) };
    for (const key of ['project_path', 'root_path', 'repo_path']) {
      if (nextInput[key] === '.' || !nextInput[key]) nextInput[key] = projectPath;
    }
    setInputText(JSON.stringify(nextInput, null, 2));
    setResult(null); setTestResult(null); setMessage('');
    listSkillVersions(selectedSkill.code).then(setVersions).catch(() => setVersions([]));
  }, [selectedSkill?.code, projectPath]);

  async function runAction(label: string, action: () => Promise<unknown>) {
    setMessage('');
    try { await action(); setMessage(`${label} completed.`); } catch (error) { setMessage(error instanceof Error ? error.message : `${label} failed`); }
  }

  async function submitExecution(event: FormEvent) {
    event.preventDefault();
    if (!selectedSkill) return;
    await runAction('Skill execution', async () => setResult((await onExecuteSkill(selectedSkill.code, agentCode, parseJsonValue(inputText))).output));
  }

  async function submitSkillTests() {
    if (!selectedSkill) return;
    await runAction('Skill tests', async () => setTestResult(await testSkill({ skill_code: selectedSkill.code, agent_code: agentCode })));
  }

  async function submitRollback(version: string) {
    if (!selectedSkill) return;
    await runAction('Skill rollback', async () => {
      await rollbackSkillVersion(selectedSkill.code, version);
      await onRefresh();
      setVersions(await listSkillVersions(selectedSkill.code));
    });
  }

  return (
    <section className="page-grid skills-page">
      <div className="panel skill-plugin-panel">
        <PanelTitle icon={<Puzzle size={17} />} title="已安装插件" action={<button className="icon-button" onClick={onRefresh}><RefreshCw size={15} /></button>} />
        <div className="skill-kpis"><KpiCard label="plugins" value={String(plugins.length)} /><KpiCard label="skills" value={String(skills.length)} /><KpiCard label="enabled" value={String(skills.filter((skill) => skill.enabled).length)} /></div>
        <div className="skill-plugin-list">
          {plugins.map((plugin) => <article key={plugin.plugin_id} className={activePlugin?.plugin_id === plugin.plugin_id ? 'active' : ''}><strong>{plugin.name}</strong><span>{plugin.plugin_id} / {plugin.version} / {plugin.source_type}</span><p>{plugin.description || 'No description.'}</p><div className="skill-actions"><button className="secondary danger" disabled={plugin.source_type === 'builtin'} onClick={() => runAction('Plugin uninstall', () => onUninstallPlugin(plugin.plugin_id))}>卸载插件</button></div></article>)}
          {!plugins.length ? <p className="empty-text">暂无已安装插件。</p> : null}
        </div>
      </div>

      <div className="panel skill-list-panel">
        <PanelTitle icon={<Puzzle size={17} />} title="Skill 列表" />
        <div className="skill-toolbar"><select value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}><option value="all">all categories</option>{categories.map((category) => <option key={category} value={category}>{category}</option>)}</select><button className="secondary" onClick={() => selectedSkill && onAddToWorkflow(selectedSkill)} disabled={!selectedSkill}>添加到 Workflow</button></div>
        <div className="skill-list">
          {filteredSkills.map((skill) => <button key={skill.code} className={selectedSkill?.code === skill.code ? 'active' : ''} onClick={() => onSelectSkill(skill.code)}><strong>{skill.name}</strong><span>{skill.code} / {skill.category} / {skill.execution_type}</span><span className="state-with-meta"><EnabledState enabled={skill.enabled} label="Skill" /><RiskBadge level={skill.risk_level} /><span>{skill.plugin_id}</span></span></button>)}
          {!filteredSkills.length ? <p className="empty-text">暂无 Skill。</p> : null}
        </div>
      </div>

      <div className="panel skill-detail-panel">
        <PanelTitle icon={<FileText size={17} />} title="插件详情" />
        {selectedSkill ? <div className="skill-detail">
          <div><h3>{selectedSkill.name}</h3><span>{selectedSkill.code}</span></div><p>{selectedSkill.description}</p>
          <dl><dt>分类</dt><dd>{selectedSkill.category}</dd><dt>来源插件</dt><dd>{selectedSkill.plugin_id}</dd><dt>执行类型</dt><dd>{selectedSkill.execution_type}</dd><dt>版本</dt><dd>{selectedSkill.version}</dd><dt>风险</dt><dd><RiskBadge level={selectedSkill.risk_level} /></dd><dt>来源格式</dt><dd>{selectedSkill.source_format}</dd><dt>状态</dt><dd><EnabledState enabled={selectedSkill.enabled} label="Skill" /></dd></dl>
          <div className="skill-tags">{(selectedSkill.permission_levels ?? []).map((level) => <span key={`level-${level}`} className={`risk-tag ${level}`}>{level}</span>)}{selectedSkill.permissions.map((permission) => <span key={permission}>{permission}</span>)}{!selectedSkill.permissions.length ? <span>no permission</span> : null}</div>
          <div className="skill-actions"><button className="secondary" onClick={() => runAction('Skill toggle', () => onSkillEnabled(selectedSkill.code, !selectedSkill.enabled))}>{selectedSkill.enabled ? '停用 Skill' : '启用 Skill'}</button><button className="secondary" onClick={() => onAddToWorkflow(selectedSkill)}>添加到 Workflow</button></div>
          <details className="skill-json"><summary>输入 / 输出 Schema</summary><pre>{JSON.stringify({ input_schema: selectedSkill.input_schema, output_schema: selectedSkill.output_schema }, null, 2)}</pre></details>
          <details className="skill-json" open><summary>契约 / 依赖 / 测试用例</summary><pre>{JSON.stringify({ contract: selectedSkill.contract, dependencies: selectedSkill.dependencies, tests: selectedSkill.tests, entrypoint: selectedSkill.entrypoint }, null, 2)}</pre></details>
          <div className="skill-version-box"><div className="skill-section-title"><strong>Skill 版本快照</strong><span>{versions.length} snapshot(s)</span></div>{versions.slice(0, 5).map((version) => <article key={`${version.skill_code}-${version.version}-${version.created_at}`}><div><strong>{version.version}</strong><span>{version.created_at}</span></div><button className="secondary" onClick={() => submitRollback(version.version)}>回滚</button></article>)}{!versions.length ? <p className="empty-text">暂无版本快照。</p> : null}</div>
        </div> : <p className="empty-text">请选择一个 Skill。</p>}
      </div>

      <div className="panel skill-approval-panel">
        <PanelTitle icon={<ShieldCheck size={17} />} title="权限审批" />
        <div className="skill-form skill-approval-form"><div className="skill-approval-guide"><strong>权限怎么判断</strong><span>审批按 skill_code + agent_code 精确匹配，不是只要有一个通过就全部通过。</span><span>skill_console：只用于 Skills 页面手动测试调用。</span><span>workflow_runner：只用于 Workflow 自动执行。Workflow 运行 Skill 时必须审批这个身份。</span></div><label>agent_code<input value={agentCode} onChange={(event) => setAgentCode(event.target.value)} /><FieldHelp>审批记录按 agent_code 隔离；Workflow 节点执行 Skill 时也会使用这个身份。</FieldHelp></label><label>reason<input value={approvalReason} onChange={(event) => setApprovalReason(event.target.value)} /></label><div className="skill-actions"><button className="secondary" disabled={!selectedSkill} onClick={() => selectedSkill && runAction('Skill approval', () => onSkillApproval(selectedSkill.code, agentCode, true, approvalReason))}>审批通过</button><button className="secondary" disabled={!selectedSkill} onClick={() => selectedSkill && runAction('Skill approval revoke', () => onSkillApproval(selectedSkill.code, agentCode, false, 'Revoked from Skills console.'))}>撤销审批</button></div></div>
        <div className={`skill-approval-state ${activeApproval?.allowed ? 'approved' : 'pending'}`}>{activeApproval?.allowed ? '当前 Agent 已审批' : '当前 Agent 未审批'}{activeApproval?.reason ? <span>{activeApproval.reason}</span> : null}</div>
        {selectedSkill ? <div className="skill-current-approval-list"><strong>当前 Skill 的审批身份</strong>{(selectedSkillApprovals.length ? selectedSkillApprovals : [{ skill_code: selectedSkill.code, agent_code: 'workflow_runner', allowed: false, reason: null, created_at: '', updated_at: '' }]).map((approval) => <article key={`${approval.skill_code}-${approval.agent_code}`}><div><span className={`mcp-approval-state ${approval.allowed ? 'approved' : 'pending'}`}>{approval.allowed ? '已审批' : '待审批'}</span><code>{approval.agent_code}</code></div>{approval.reason ? <small>{approval.reason}</small> : null}<div className="skill-actions"><button className="secondary" onClick={() => { setAgentCode(approval.agent_code); runAction('Skill approval revoke', () => onSkillApproval(selectedSkill.code, approval.agent_code, false, `Revoked ${approval.agent_code} from Skills console.`)); }}>撤销这个身份</button>{!approval.allowed ? <button className="secondary" onClick={() => { setAgentCode(approval.agent_code); runAction('Skill approval', () => onSkillApproval(selectedSkill.code, approval.agent_code, true, `Approved ${approval.agent_code} from Skills console.`)); }}>审批这个身份</button> : null}</div></article>)}{!selectedSkillApprovals.some((approval) => approval.agent_code === 'workflow_runner') ? <button className="secondary" onClick={() => { setAgentCode('workflow_runner'); runAction('Skill approval', () => onSkillApproval(selectedSkill.code, 'workflow_runner', true, 'Approved workflow_runner from Skills console.')); }}>审批 workflow_runner</button> : null}</div> : null}
        <div className="skill-approval-list">{approvals.slice(0, 8).map((approval) => <article key={`${approval.skill_code}-${approval.agent_code}`}><strong>{approval.skill_code}</strong><span>{approval.agent_code} / {approval.allowed ? 'allowed' : 'blocked'}</span></article>)}</div>
      </div>

      <div className="panel skill-execute-panel">
        <PanelTitle icon={<Play size={17} />} title="测试调用" />
        <form className="skill-form" onSubmit={submitExecution}><label>input JSON<textarea value={inputText} onChange={(event) => setInputText(event.target.value)} /><FieldHelp>这里是传给 Skill 的输入。项目类 Skill 会读取 project_path / root_path / repo_path。</FieldHelp></label><button className="primary" disabled={!selectedSkill || !selectedSkill.enabled} type="submit"><Play size={16} />测试调用 Skill</button><button className="secondary" disabled={!selectedSkill || !selectedSkill.enabled} type="button" onClick={submitSkillTests}>运行自带测试</button></form>
        <div className="skill-execute-output">{message ? <p className="skill-message">{message}</p> : null}{testResult ? <div className="skill-test-summary"><strong>测试结果：{testResult.passed}/{testResult.total} passed</strong><pre>{JSON.stringify(testResult.results, null, 2)}</pre></div> : null}{result ? <pre className="skill-result">{JSON.stringify(result, null, 2)}</pre> : <p className="empty-text">暂无测试输出。</p>}</div>
      </div>

      <div className="panel skill-log-panel">
        <PanelTitle icon={<History size={17} />} title="执行日志" />
        <div className="skill-log-list">{logs.map((log) => <article key={log.log_id} className={`skill-log-item ${log.status}`}><div><strong>{log.skill_code}</strong><span>{log.status} / {log.latency_ms}ms / {log.created_at}</span></div>{log.error_message ? <p>{log.error_message}</p> : <p>{summarizeValue(log.output)}</p>}<details className="skill-json"><summary>完整 JSON</summary><pre>{JSON.stringify(log, null, 2)}</pre></details></article>)}{!logs.length ? <p className="empty-text">暂无 Skill 执行日志。</p> : null}</div>
      </div>
    </section>
  );
}

function KpiCard({ label, value }: { label: string; value: string }) { return <div className="kpi-card"><span>{label}</span><strong>{value}</strong></div>; }
function parseJsonValue(text: string): Record<string, unknown> { try { return JSON.parse(text) as Record<string, unknown>; } catch { return {}; } }
function summarizeValue(value: unknown) { const text = JSON.stringify(value); return text.length > 240 ? `${text.slice(0, 237)}...` : text; }
