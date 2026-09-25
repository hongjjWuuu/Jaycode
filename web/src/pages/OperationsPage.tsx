import { Activity, AlertTriangle, RefreshCw, Server, Users } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { ApiErrorNotice } from '../components/ApiErrorNotice';
import { PanelTitle } from '../components/DisplayPrimitives';
import { getOperationsOverview } from '../services/operations';
import type { OperationsOverview, OperationsTask } from '../types';

function TaskRows({ title, tasks, onOpen }: { title: string; tasks: OperationsTask[]; onOpen: (taskId: string) => void }) {
  return <div className="panel operations-task-list"><PanelTitle icon={<Activity size={17} />} title={title} />
    {tasks.length ? <div className="task-list">{tasks.map((task) => <button className="task-item" key={task.task_id} onClick={() => onOpen(task.task_id)}><strong>{task.task_id}</strong><span>{task.status}</span><small>{task.updated_at || task.created_at}</small></button>)}</div> : <p className="empty-text">暂无任务。</p>}
  </div>;
}

export function OperationsPage({ onOpenTask }: { onOpenTask: (taskId: string) => void }) {
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'warning' | 'critical'>('all');

  const refresh = useCallback(async () => {
    setLoading(true);
    try { setOverview(await getOperationsOverview()); setError(null); }
    catch (exc) { setError(exc); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    refresh().catch(() => undefined);
    const timer = window.setInterval(() => refresh().catch(() => undefined), 15_000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const alerts = (overview?.alerts ?? []).filter((alert) => filter === 'all' || alert.severity === filter);
  return <section className="page-grid operations-page">
    <div className="panel"><PanelTitle icon={<Server size={17} />} title="任务运营中心" action={<button className="secondary" onClick={() => refresh()} disabled={loading}>{loading ? <RefreshCw className="spin" size={15} /> : '刷新'}</button>} />
      <p className="small-muted">每 15 秒刷新；此页只展示状态并跳转至已有审核/任务操作，不会重启 Worker 或修改数据库。</p>
      <div className="state-summary"><span>数据库：{overview?.readiness.database ? 'ready' : 'not ready'}</span><span>Supervisor：{overview?.supervisor.status ?? 'unknown'}</span><span>活跃 Worker：{overview?.supervisor.active_workers ?? 0}/{overview?.supervisor.worker_count ?? 0}</span><span>重启：{overview?.supervisor.restart_count ?? 0}</span></div>
      <ApiErrorNotice error={error} />
    </div>
    <div className="panel"><PanelTitle icon={<AlertTriangle size={17} />} title="运营告警" action={<select value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="all">全部</option><option value="warning">警告</option><option value="critical">严重</option></select>} />
      {alerts.length ? <div className="operations-alerts">{alerts.map((alert) => <article key={alert.code} className={`operations-alert ${alert.severity}`}><strong>{alert.code}</strong><span>{alert.message}</span></article>)}</div> : <p className="empty-text">当前没有匹配的告警。</p>}
    </div>
    <div className="panel"><PanelTitle icon={<Users size={17} />} title="队列状态" />
      <div className="benchmark-result-grid">{Object.entries(overview?.task_counts ?? {}).map(([status, count]) => <article key={status} className="benchmark-result-item"><strong>{status}</strong><span>{count}</span></article>)}</div>
      {overview?.oldest_queued_task ? <button className="secondary" onClick={() => onOpenTask(overview.oldest_queued_task!.task_id)}>打开最早排队任务：{overview.oldest_queued_task.task_id}</button> : null}
    </div>
    <TaskRows title="等待审核" tasks={overview?.waiting_review ?? []} onOpen={onOpenTask} />
    <TaskRows title="最近失败" tasks={overview?.recent_failed ?? []} onOpen={onOpenTask} />
  </section>;
}
