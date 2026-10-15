import { Activity, CheckCircle2, FolderOpen, FolderSearch, Play, RefreshCw, Save } from 'lucide-react';
import { FormEvent, useState } from 'react';
import { PanelTitle } from '../components/DisplayPrimitives';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import { TaskTimeline } from '../components/TaskTimeline';
import { EventDetail, ResumePanel, ReviewBox, RunOutputs } from '../components/run/RunDetails';
import type { AgentEvent, ProjectBrowserResult, ProjectBrowserRoot, ProjectLibraryItem, ResolvedProject, ResumeSnapshot, WorkflowRecord } from '../types';
import { browseProjectDirectories, listProjectBrowserRoots } from '../services/projects';

type Props = {
  goal: string; projectPath: string; resolvedProject: ResolvedProject | null;
  projectValidationStatus: 'idle' | 'validating' | 'valid' | 'invalid'; projectValidationError: string;
  projectLibrary: ProjectLibraryItem[];
  requiresProject: boolean; projectReasons: string[]; knowledgeScopeMissing: boolean;
  maxFiles: number; requireReview: boolean; running: boolean; submitLabel: string; error: unknown;
  events: AgentEvent[]; latestTaskId: string; latestStatus: string; workflowName: string; workflowId: string;
  workflows: WorkflowRecord[]; taskNeedsReview: boolean; reviewComment: string; resumeSnapshots: ResumeSnapshot[];
  selectedEvent: AgentEvent | null; toolCalls: string[]; agentOutputs: string[];
  onReviewCommentChange: (value: string) => void; onReview: (action: 'approve' | 'reject' | 'revise') => void;
  onReviewAction: (action: string, payload?: Record<string, unknown>) => void; onGoalChange: (value: string) => void;
  onProjectPathChange: (value: string) => void; onProjectValidate: () => Promise<ResolvedProject>;
  onTemporaryProjectSelect: (path: string) => Promise<ResolvedProject>; onProjectLibraryRefresh: () => Promise<void>; onSavedProjectSelect: (project: ProjectLibraryItem) => Promise<void>; onSaveCurrentProject: () => Promise<ProjectLibraryItem>;
  onMaxFilesChange: (value: number) => void; onRequireReviewChange: (value: boolean) => void;
  onWorkflowSelect: (workflowId: string) => void; onWorkflowsRefresh: () => void | Promise<void>;
  onSubmit: (event: FormEvent) => void;
};

function ProjectDirectoryBrowser({ onChoose }: { onChoose: (path: string) => Promise<unknown> }) {
  const [open, setOpen] = useState(false); const [roots, setRoots] = useState<ProjectBrowserRoot[]>([]); const [current, setCurrent] = useState<ProjectBrowserResult | null>(null); const [error, setError] = useState('');
  const loadRoots = async () => { setError(''); try { setRoots(await listProjectBrowserRoots()); setOpen(true); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } };
  const browse = async (rootId: string, relativePath = '') => { try { setError(''); setCurrent(await browseProjectDirectories(rootId, relativePath)); } catch (cause) { setError(cause instanceof Error ? cause.message : String(cause)); } };
  const choose = async () => { if (!current) return; await onChoose(current.resolved_path); setOpen(false); };
  return <div className="project-browser"><button type="button" className="secondary" onClick={() => void loadRoots()}><FolderOpen size={16} />浏览文件夹</button>{open ? <div className="project-browser-popover"><strong>从允许目录中选择项目</strong>{!current ? <div className="project-browser-list">{roots.map((root) => <button type="button" key={root.root_id} onClick={() => void browse(root.root_id)}>{root.name}</button>)}</div> : <><div className="project-browser-path"><button type="button" onClick={() => void browse(current.root_id)}>{current.root_name}</button><span>/{current.relative_path}</span></div><div className="project-browser-list">{current.directories.map((directory) => <button type="button" key={directory.relative_path} onClick={() => void browse(current.root_id, directory.relative_path)}><FolderOpen size={14} />{directory.name}</button>)}</div><button type="button" className="primary compact-button" onClick={() => void choose()}>选择当前文件夹</button></>}<button type="button" className="text-button" onClick={() => setOpen(false)}>关闭</button>{error ? <small className="field-error">{error}</small> : null}</div> : null}</div>;
}

export function RunPage(props: Props) {
  const { goal, projectPath, resolvedProject, projectValidationStatus, projectValidationError, requiresProject,
    projectReasons, knowledgeScopeMissing, maxFiles, requireReview, running, submitLabel, error, events, projectLibrary,
    latestTaskId, latestStatus, workflowName, workflowId, workflows, taskNeedsReview, reviewComment,
    resumeSnapshots, selectedEvent, toolCalls, agentOutputs, onReviewCommentChange, onReview, onReviewAction,
    onGoalChange, onProjectPathChange, onProjectValidate, onTemporaryProjectSelect, onProjectLibraryRefresh, onSavedProjectSelect, onSaveCurrentProject, onMaxFilesChange, onRequireReviewChange,
    onWorkflowSelect, onWorkflowsRefresh, onSubmit } = props;
  const projectMissing = requiresProject && !projectPath.trim();
  const projectUnverified = requiresProject && projectValidationStatus !== 'valid';
  const runDisabled = running || projectValidationStatus === 'validating' || projectMissing || projectUnverified || knowledgeScopeMissing;
  const disabledReason = knowledgeScopeMissing ? '知识节点尚未选择知识范围' : projectMissing
    ? '当前流程需要项目，请填写并验证项目路径' : projectUnverified ? '请先验证项目路径' : '';

  return <section className="page-grid run-page"><div className="panel run-panel">
    <PanelTitle icon={<Play size={17} />} title="任务入口" />
    <div className={`project-requirement ${requiresProject ? 'required' : 'optional'}`}><strong>{requiresProject ? '该流程会扫描本地项目' : '该流程不扫描本地项目'}</strong><small>{projectReasons.length ? projectReasons.join('；') : '项目路径可留空。'}</small></div>
    <form className="run-form" onSubmit={onSubmit}>
      <label>目标<textarea value={goal} onChange={(event) => onGoalChange(event.target.value)} /></label>
      <label>我的项目<div className="project-path-row"><select aria-label="我的项目" value="" onChange={(event) => { const selected = projectLibrary.find((item) => item.registered_project_id === event.target.value); if (selected) void onSavedProjectSelect(selected); }}><option value="">选择最近或已保存项目</option>{projectLibrary.map((project) => <option key={project.registered_project_id} value={project.registered_project_id}>{project.name}{project.last_used_at ? ' · 最近使用' : ''}</option>)}</select><button type="button" className="secondary" onClick={() => void onProjectLibraryRefresh()}><RefreshCw size={15} />刷新</button></div></label>
      <div className="project-source-actions"><ProjectDirectoryBrowser onChoose={onTemporaryProjectSelect} /><small>选择后仅本次使用；验证成功后可保存到我的项目。</small></div>
      <label>手动项目路径（可选）<div className="project-path-row"><input value={projectPath} placeholder="例如 . 或 D:\\projects\\demo" onChange={(event) => onProjectPathChange(event.target.value)} onBlur={() => { if (projectPath.trim() && projectValidationStatus === 'idle') void onProjectValidate().catch(() => undefined); }} /><button type="button" className="secondary" disabled={!projectPath.trim() || projectValidationStatus === 'validating'} onClick={() => void onProjectValidate().catch(() => undefined)}><FolderSearch size={16} />{projectValidationStatus === 'validating' ? '验证中' : '验证项目'}</button></div></label>
      {resolvedProject ? <div className="resolved-project"><CheckCircle2 size={17} /><div><strong>{resolvedProject.project_name}</strong><span>{resolvedProject.input_path} → {resolvedProject.resolved_path}</span><small>ID: {resolvedProject.project_id} · {resolvedProject.file_count} 文件 · {resolvedProject.directory_count} 目录</small></div><button type="button" className="secondary compact-button" onClick={() => void onSaveCurrentProject()}><Save size={14} />保存到我的项目</button></div> : null}
      {projectValidationError ? <p className="field-error">{projectValidationError}</p> : null}
      <div className="run-target-summary"><strong>本次运行对象</strong><span>{resolvedProject ? resolvedProject.resolved_path : requiresProject ? '尚未验证项目' : '本次运行不扫描本地项目'}</span></div>
      <label>已保存 Workflow<select aria-label="已保存 Workflow" value={workflowId} onChange={(event) => onWorkflowSelect(event.target.value)}><option value="">当前画布：{workflowName}</option>{workflows.map((workflow) => <option key={workflow.workflow_id} value={workflow.workflow_id}>{workflow.name}</option>)}</select></label>
      <button type="button" className="secondary" onClick={() => void onWorkflowsRefresh()}>刷新已保存流程</button>
      <label>最大文件数<input type="number" min={1} value={maxFiles} onChange={(event) => onMaxFilesChange(Number(event.target.value))} /></label>
      <label className="toggle-row"><input type="checkbox" checked={requireReview} onChange={(event) => onRequireReviewChange(event.target.checked)} />人工审核</label>
      <button className="primary" disabled={runDisabled}>{running ? <RefreshCw className="spin" size={17} /> : <Play size={17} />}{running ? '执行中...' : submitLabel}</button>{disabledReason ? <small className="run-disabled-reason">{disabledReason}</small> : null}
    </form><ApiErrorNotice error={error} />
  </div><div className="panel timeline-large"><PanelTitle icon={<Activity size={17} />} title="执行过程" /><TaskTimeline events={events} /></div><div className="panel state-panel"><PanelTitle icon={<Activity size={17} />} title="结果总览" /><dl className="state-summary"><dt>Task</dt><dd>{latestTaskId || '未运行'}</dd><dt>Status</dt><dd>{latestStatus}</dd><dt>Workflow</dt><dd>{workflowName}</dd></dl>{taskNeedsReview ? <ReviewBox comment={reviewComment} onCommentChange={onReviewCommentChange} onReview={onReview} onReviewAction={onReviewAction} /> : null}<ResumePanel snapshots={resumeSnapshots} events={events} /><EventDetail event={selectedEvent} /><RunOutputs toolCalls={toolCalls} agentOutputs={agentOutputs} /></div></section>;
}
