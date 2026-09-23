import { Check, Save, Workflow } from 'lucide-react';
import type { PointerEvent, Ref } from 'react';
import { FieldHelp, PanelTitle } from '../components/DisplayPrimitives';
import { EdgeConfig, type EdgeConfigProps } from '../components/workflow/EdgeConfig';
import { NodeConfig, type NodeConfigProps } from '../components/workflow/NodeConfig';
import { WorkflowCanvas, type WorkflowCanvasProps } from '../components/workflow/WorkflowCanvas';
import type { WorkflowEdge, WorkflowNode, WorkflowRecord, WorkflowValidation } from '../types';

type Props = { name: string; description: string; validation: WorkflowValidation | null; workflows: WorkflowRecord[]; canvas: WorkflowCanvasProps; nodeConfig: NodeConfigProps; edgeConfig: EdgeConfigProps; onNameChange: (value: string) => void; onDescriptionChange: (value: string) => void; onSave: () => void; onValidate: () => void; onLoad: (workflow: WorkflowRecord) => void; onRefresh: () => void; };
export function WorkflowPage({ name, description, validation, workflows, canvas, nodeConfig, edgeConfig, onNameChange, onDescriptionChange, onSave, onValidate, onLoad, onRefresh }: Props) {
  return <section className="page-grid workflow-page"><div className="panel workflow-sidebar"><PanelTitle icon={<Workflow size={17} />} title="Workflow" /><div className="workflow-fields"><input value={name} onChange={(event) => onNameChange(event.target.value)} /><FieldHelp>Workflow 名称会写入任务记录和历史模板。</FieldHelp><textarea value={description} onChange={(event) => onDescriptionChange(event.target.value)} /><FieldHelp>描述流程用途、节点顺序和适用场景。</FieldHelp><button className="secondary" onClick={onSave}><Save size={15} />保存 Workflow</button><button className="secondary" onClick={onValidate}><Check size={15} />校验 Workflow</button></div>{validation ? <pre className="workflow-validation">{JSON.stringify(validation, null, 2)}</pre> : null}<PanelTitle title="已保存" action={<button className="secondary" onClick={onRefresh}>刷新</button>} /><div className="saved-workflow-list">{workflows.map((item) => <button key={item.workflow_id} onClick={() => onLoad(item)}>{item.name}</button>)}</div></div><div className="panel canvas-panel"><PanelTitle icon={<Workflow size={17} />} title="图形化流程" /><WorkflowCanvas {...canvas} /></div><div className="panel config-panel"><NodeConfig {...nodeConfig} /><EdgeConfig {...edgeConfig} /></div></section>;
}
