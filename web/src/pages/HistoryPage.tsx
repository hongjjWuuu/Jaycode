import { Activity, FileText, History, RefreshCw, RotateCcw, Trash2, X } from 'lucide-react';
import { PanelTitle } from '../components/DisplayPrimitives';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import { useMemo, useState } from 'react';
import { TaskTimeline } from '../components/TaskTimeline';
import type { AgentEvent, TaskBatchMutationResult, TaskSummary } from '../types';

type AsyncResult = void | Promise<void>;
type Props = { tasks: TaskSummary[]; deletedTasks: TaskSummary[]; taskActor: { actor_id: string; role: string } | null; selectedTaskId: string; events: AgentEvent[]; finalReport: string; onOpen: (taskId: string) => AsyncResult; onRefresh: () => Promise<void>; onRefreshDeleted: () => Promise<void>; onDelete: (taskIds: string[]) => Promise<TaskBatchMutationResult>; onRestore: (taskIds: string[]) => Promise<TaskBatchMutationResult>; };
const deletable = new Set(['completed', 'failed', 'rejected', 'cancelled']);
const retentionText = (value?: string) => !value ? '保留期未知' : `剩余 ${Math.max(0, Math.ceil((new Date(value).getTime() - Date.now()) / 86_400_000))} 天`;

export function HistoryPage({ tasks, deletedTasks, taskActor, selectedTaskId, events, finalReport, onOpen, onRefresh, onRefreshDeleted, onDelete, onRestore }: Props) {
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState(''); const [selectionMode, setSelectionMode] = useState(false); const [recycleBin, setRecycleBin] = useState(false); const [selected, setSelected] = useState<string[]>([]);
  const visibleTasks = recycleBin ? deletedTasks : tasks;
  const canMutate = (task: TaskSummary) => !taskActor || ['admin', 'system-agent'].includes(taskActor.role) || task.actor_id === taskActor.actor_id;
  const selectableIds = useMemo(() => visibleTasks.filter((task) => (recycleBin || deletable.has(task.status)) && canMutate(task)).map((task) => task.task_id), [recycleBin, taskActor, visibleTasks]);
  function runAction(action: () => AsyncResult) { setError(null); try { Promise.resolve(action()).catch(setError); } catch (cause) { setError(cause); } }
  const exitSelection = () => { setSelectionMode(false); setSelected([]); };
  const toggleSelection = (taskId: string) => setSelected((items) => items.includes(taskId) ? items.filter((item) => item !== taskId) : [...items, taskId]);
  const selectAll = () => setSelected(selected.length === selectableIds.length ? [] : selectableIds);
  const changeView = (deleted: boolean) => runAction(async () => { setRecycleBin(deleted); exitSelection(); if (deleted) await onRefreshDeleted(); else await onRefresh(); });
  const submitDelete = () => runAction(async () => { if (!selected.length || !window.confirm(`确认将 ${selected.length} 个任务移入回收站吗？任务将在 30 天后永久清理。`)) return; const result = await onDelete(selected); setNotice(`已移入回收站 ${result.deleted.length} 项${result.skipped.length ? `，跳过 ${result.skipped.length} 项` : ''}。`); exitSelection(); });
  const submitRestore = () => runAction(async () => { if (!selected.length) return; const result = await onRestore(selected); setNotice(`已恢复 ${result.restored.length} 项${result.skipped.length ? `，跳过 ${result.skipped.length} 项` : ''}。`); exitSelection(); });
  return <section className="page-grid history-page">
    <div className="panel history-list-panel"><PanelTitle icon={<History size={17} />} title={recycleBin ? '任务回收站' : '历史任务'} action={<div className="history-title-actions"><button className="icon-button" aria-label="刷新任务" onClick={() => runAction(recycleBin ? onRefreshDeleted : onRefresh)}><RefreshCw size={15} /></button><button className="secondary compact-button" onClick={() => changeView(!recycleBin)}>{recycleBin ? '历史任务' : '回收站'}</button></div>} /><div className="history-selection-toolbar">{!selectionMode ? <button className="secondary compact-button" onClick={() => { setSelectionMode(true); setNotice(''); }}>{recycleBin ? '选择恢复' : '选择删除'}</button> : <><button className="secondary compact-button" onClick={selectAll}>{selected.length === selectableIds.length && selectableIds.length ? '取消全选' : '全选当前列表'}</button><span>已选 {selected.length} 项</span><button className={recycleBin ? 'primary compact-button' : 'danger compact-button'} disabled={!selected.length} onClick={recycleBin ? submitRestore : submitDelete}>{recycleBin ? <><RotateCcw size={14} /> 恢复所选</> : <><Trash2 size={14} /> 删除所选</>}</button><button className="icon-button" aria-label="取消选择" onClick={exitSelection}><X size={15} /></button></>}</div><div className="history-message-area"><ApiErrorNotice error={error} />{notice ? <p className="history-notice" role="status">{notice}</p> : null}</div><div className="task-list">{visibleTasks.map((task) => { const allowed = canMutate(task); const blockedReason = !allowed ? '只能操作自己创建的任务。' : !recycleBin && !deletable.has(task.status) ? '运行、暂停或等待审核的任务不可删除' : undefined; return <article key={task.task_id} className={`history-task-row ${task.task_id === selectedTaskId ? 'active' : ''}`}>{selectionMode ? <input aria-label={`选择 ${task.goal}`} type="checkbox" checked={selected.includes(task.task_id)} disabled={Boolean(blockedReason)} onChange={() => toggleSelection(task.task_id)} title={blockedReason} /> : null}<button disabled={recycleBin} onClick={() => runAction(() => onOpen(task.task_id))}><span>{task.goal}</span><small>{task.status}</small><small>{task.project_path ? `项目：${task.project_path}` : '未扫描本地项目'}</small>{recycleBin ? <small>{retentionText(task.purge_after)}</small> : task.project_id ? <small>ID：{task.project_id}</small> : null}</button></article>; })}{!visibleTasks.length ? <p className="empty-text">{recycleBin ? '回收站为空。' : '暂无历史任务。'}</p> : null}</div></div>
    <div className="panel timeline-large"><PanelTitle icon={<Activity size={17} />} title="任务事件回放" /><TaskTimeline events={events} empty="选择历史任务后，这里会显示完整执行事件。" /></div>
    <div className="panel report-preview-panel"><PanelTitle icon={<FileText size={17} />} title="报告预览" /><div className="markdown-view"><pre>{finalReport || '选择历史任务后查看报告。'}</pre></div></div>
  </section>;
}
