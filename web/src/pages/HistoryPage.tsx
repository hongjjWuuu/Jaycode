import { Activity, FileText, History, RefreshCw } from 'lucide-react';
import { PanelTitle } from '../components/DisplayPrimitives';
import { TaskTimeline } from '../components/TaskTimeline';
import type { AgentEvent, TaskSummary } from '../types';

type Props = { tasks: TaskSummary[]; selectedTaskId: string; events: AgentEvent[]; finalReport: string; onOpen: (taskId: string) => void; onRefresh: () => Promise<void>; };
export function HistoryPage({ tasks, selectedTaskId, events, finalReport, onOpen, onRefresh }: Props) {
  return <section className="page-grid history-page">
    <div className="panel history-list-panel"><PanelTitle icon={<History size={17} />} title="历史任务" action={<button className="icon-button" onClick={() => onRefresh()}><RefreshCw size={15} /></button>} /><div className="task-list">{tasks.map((task) => <button key={task.task_id} className={task.task_id === selectedTaskId ? 'active' : ''} onClick={() => onOpen(task.task_id)}><span>{task.goal}</span><small>{task.status}</small></button>)}{!tasks.length ? <p className="empty-text">暂无历史任务。</p> : null}</div></div>
    <div className="panel timeline-large"><PanelTitle icon={<Activity size={17} />} title="任务事件回放" /><TaskTimeline events={events} empty="选择历史任务后，这里会显示完整执行事件。" /></div>
    <div className="panel report-preview-panel"><PanelTitle icon={<FileText size={17} />} title="报告预览" /><div className="markdown-view"><pre>{finalReport || '选择历史任务后查看报告。'}</pre></div></div>
  </section>;
}
