import { Check, FilePlus2, Plus, Save, Trash2, Workflow } from 'lucide-react';
import { useState } from 'react';
import { FieldHelp, PanelTitle } from '../components/DisplayPrimitives';
import { EdgeConfig, type EdgeConfigProps } from '../components/workflow/EdgeConfig';
import { NodeConfig, type NodeConfigProps } from '../components/workflow/NodeConfig';
import { WorkflowCanvas, type WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import type { WorkflowRecord, WorkflowValidation } from '../types';

type Props = { name: string; description: string; validation: WorkflowValidation | null; workflows: WorkflowRecord[]; canvas: WorkflowCanvasProps; nodeConfig: NodeConfigProps; edgeConfig: EdgeConfigProps; onNameChange: (value: string) => void; onDescriptionChange: (value: string) => void; onNew: () => void; onAddNode: (type: string) => void; onSave: () => void | Promise<void>; onValidate: () => void | Promise<void>; onLoad: (workflow: WorkflowRecord) => void | Promise<void>; onDelete: (workflowId: string) => void | Promise<unknown>; onRefresh: () => void | Promise<void>; };
const nodeActions = [['planner', '规划'], ['agent', '分析 Agent'], ['human_review', '人工审核'], ['reporter', '报告'], ['rag', '知识检索'], ['mcp_tool', 'MCP 工具'], ['skill', 'Skill'], ['supervisor', '监督']] as const;
const workflowTitle = (name: string) => /^\d+$/.test(name.trim()) ? `流程 ${name.trim()}` : name.trim() || '未命名 Workflow';
const formatTime = (value: string) => { const time = new Date(value); return Number.isNaN(time.getTime()) ? (value || '未知时间') : time.toLocaleString('zh-CN', { hour12: false }); };
export function WorkflowPage({ name, description, validation, workflows, canvas, nodeConfig, edgeConfig, onNameChange, onDescriptionChange, onNew, onAddNode, onSave, onValidate, onLoad, onDelete, onRefresh }: Props) {
  const [error, setError] = useState<unknown>(null);
  const runAction = (action: () => void | Promise<unknown>) => {
    setError(null);
    try { Promise.resolve(action()).catch(setError); } catch (cause) { setError(cause); }
  };
  const removeWorkflow = (item: WorkflowRecord) => {
    if (window.confirm(`确定删除“${workflowTitle(item.name)}”吗？此操作无法恢复。`)) runAction(() => onDelete(item.workflow_id));
  };
  return <section className="page-grid workflow-page"><div className="panel workflow-sidebar"><PanelTitle icon={<Workflow size={17} />} title="Workflow" /><ApiErrorNotice error={error} /><div className="workflow-fields"><button type="button" className="secondary" onClick={onNew}><FilePlus2 size={15} />新建画布流程</button><label>流程名称<input value={name} onChange={(event) => onNameChange(event.target.value)} /></label><FieldHelp>新建后先添加节点，再保存为可复用的 Workflow。</FieldHelp><label>流程描述<textarea value={description} onChange={(event) => onDescriptionChange(event.target.value)} /></label><FieldHelp>描述流程用途、节点顺序和适用场景。</FieldHelp><div className="workflow-node-palette"><strong>添加流程节点</strong><span>点击添加；新节点会接在最后一个节点之后，仍可在画布上调整连接。</span><div>{nodeActions.map(([type, label]) => <button type="button" className="secondary" key={type} onClick={() => onAddNode(type)}><Plus size={13} />{label}</button>)}</div></div><button className="secondary" onClick={() => runAction(onSave)}><Save size={15} />保存 Workflow</button><button className="secondary" onClick={() => runAction(onValidate)}><Check size={15} />校验 Workflow</button></div>{validation ? <pre className="workflow-validation">{JSON.stringify(validation, null, 2)}</pre> : null}<PanelTitle title={`已保存（${workflows.length}）`} action={<button className="secondary" onClick={() => runAction(onRefresh)}>刷新</button>} /><div className="saved-workflow-list">{workflows.length ? workflows.map((item) => <article className="saved-workflow-card" key={item.workflow_id}><button className="saved-workflow-load" onClick={() => runAction(() => onLoad(item))}><strong>{workflowTitle(item.name)}</strong><span>{item.description?.trim() || '未填写流程描述'}</span><small>{item.nodes.length} 个节点 · {item.edges.length} 条连线</small><time>更新于 {formatTime(item.updated_at)}</time></button><button type="button" className="icon-button saved-workflow-delete" aria-label={`删除 ${workflowTitle(item.name)}`} onClick={() => removeWorkflow(item)}><Trash2 size={14} /></button></article>) : <p className="empty-text">还没有已保存流程。新建画布并保存后会显示在这里。</p>}</div></div><div className="panel canvas-panel"><PanelTitle icon={<Workflow size={17} />} title="图形化流程" /><WorkflowCanvas {...canvas} /></div><div className="panel config-panel"><NodeConfig {...nodeConfig} /><EdgeConfig {...edgeConfig} /></div></section>;
}
