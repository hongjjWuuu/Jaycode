import { Activity, CheckCircle2, FolderSearch, Play, RefreshCw } from 'lucide-react';
import { FormEvent } from 'react';
import { PanelTitle } from '../components/DisplayPrimitives';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import { TaskTimeline } from '../components/TaskTimeline';
import { EventDetail, ResumePanel, ReviewBox, RunOutputs } from '../components/run/RunDetails';
import type { AgentEvent, ResolvedProject, ResumeSnapshot, WorkflowRecord } from '../types';

type Props = {
  goal: string; projectPath: string; resolvedProject: ResolvedProject | null;
  projectValidationStatus: 'idle' | 'validating' | 'valid' | 'invalid'; projectValidationError: string;
  requiresProject: boolean; projectReasons: string[]; knowledgeScopeMissing: boolean;
  maxFiles: number; requireReview: boolean; running: boolean; submitLabel: string; error: unknown;
  events: AgentEvent[]; latestTaskId: string; latestStatus: string; workflowName: string; workflowId: string;
  workflows: WorkflowRecord[]; taskNeedsReview: boolean; reviewComment: string; resumeSnapshots: ResumeSnapshot[];
  selectedEvent: AgentEvent | null; toolCalls: string[]; agentOutputs: string[];
  onReviewCommentChange: (value: string) => void; onReview: (action: 'approve' | 'reject' | 'revise') => void;
  onReviewAction: (action: string, payload?: Record<string, unknown>) => void; onGoalChange: (value: string) => void;
  onProjectPathChange: (value: string) => void; onProjectValidate: () => Promise<ResolvedProject>;
  onMaxFilesChange: (value: number) => void; onRequireReviewChange: (value: boolean) => void;
  onWorkflowSelect: (workflowId: string) => void; onWorkflowsRefresh: () => void | Promise<void>;
  onSubmit: (event: FormEvent) => void;
};

export function RunPage(props: Props) {
  const { goal, projectPath, resolvedProject, projectValidationStatus, projectValidationError, requiresProject,
    projectReasons, knowledgeScopeMissing, maxFiles, requireReview, running, submitLabel, error, events,
    latestTaskId, latestStatus, workflowName, workflowId, workflows, taskNeedsReview, reviewComment,
    resumeSnapshots, selectedEvent, toolCalls, agentOutputs, onReviewCommentChange, onReview, onReviewAction,
    onGoalChange, onProjectPathChange, onProjectValidate, onMaxFilesChange, onRequireReviewChange,
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
      <label>项目路径<div className="project-path-row"><input value={projectPath} placeholder="例如 . 或 D:\\projects\\demo" onChange={(event) => onProjectPathChange(event.target.value)} onBlur={() => { if (projectPath.trim() && projectValidationStatus === 'idle') void onProjectValidate().catch(() => undefined); }} /><button type="button" className="secondary" disabled={!projectPath.trim() || projectValidationStatus === 'validating'} onClick={() => void onProjectValidate().catch(() => undefined)}><FolderSearch size={16} />{projectValidationStatus === 'validating' ? '验证中' : '验证项目'}</button></div></label>
      {resolvedProject ? <div className="resolved-project"><CheckCircle2 size={17} /><div><strong>{resolvedProject.project_name}</strong><span>{resolvedProject.input_path} → {resolvedProject.resolved_path}</span><small>ID: {resolvedProject.project_id} · {resolvedProject.file_count} 文件 · {resolvedProject.directory_count} 目录</small></div></div> : null}
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
