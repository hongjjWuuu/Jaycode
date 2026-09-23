import { Check, RefreshCw, X } from 'lucide-react';
import { FieldHelp, PanelTitle } from '../DisplayPrimitives';
import { OutputList } from '../OutputList';
import type { AgentEvent, ResumeSnapshot } from '../../types';

export function ReviewBox({ comment, onCommentChange, onReview, onReviewAction }: { comment: string; onCommentChange: (value: string) => void; onReview: (action: 'approve' | 'reject' | 'revise') => void; onReviewAction: (action: string, payload?: Record<string, unknown>) => void }) {
  return <div className="review-box"><PanelTitle icon={<Check size={16} />} title="人工审核" /><textarea value={comment} onChange={(event) => onCommentChange(event.target.value)} placeholder="填写审核意见" /><FieldHelp>通过会继续暂停的 Workflow；修改/拒绝会保留你的意见到任务事件里。</FieldHelp><FieldHelp>如果暂停节点开启了“执行前确认”并设置 retry_count，拒绝/修改会先消耗重试次数并重新等待确认；次数用完后才结束为拒绝。</FieldHelp><div className="review-actions"><button onClick={() => onReview('approve')}><Check size={15} />通过</button><button onClick={() => onReview('revise')}><RefreshCw size={15} />修改</button><button onClick={() => onReview('reject')}><X size={15} />拒绝</button></div><div className="review-extra-actions"><button onClick={() => onReviewAction('rerun_analysis')}>深入分析</button><button onClick={() => onReviewAction('focus_module', { module: comment || 'selected module' })}>聚焦模块</button><button onClick={() => onReviewAction('save_knowledge')}>保存知识</button><button onClick={() => onReviewAction('learning_task')}>学习任务</button></div></div>;
}

export function EventDetail({ event }: { event: AgentEvent | null }) {
  if (!event) return <div className="detail-box"><strong>节点详情</strong><p>点击执行时间线中的节点，查看该步骤的输出、状态和后续可追问方向。</p></div>;
  const output = event.data?.output;
  return <div className="detail-box"><strong>{String(event.data?.node_name ?? event.node ?? event.type)}</strong><p>{event.content}</p><dl><dt>Agent</dt><dd>{event.agent ?? 'runtime'}</dd><dt>Status</dt><dd>{event.status ?? 'unknown'}</dd></dl>{output ? <pre>{summarize(output)}</pre> : null}</div>;
}

export function ResumePanel({ snapshots = [], events = [] }: { snapshots?: ResumeSnapshot[]; events?: AgentEvent[] }) {
  const records = snapshots.length ? snapshots : deriveSnapshots(events);
  if (!records.length) return null;
  return <div className="resume-panel"><PanelTitle icon={<RefreshCw size={16} />} title="Resume 可视化" />{records.slice(-3).reverse().map((snapshot, index) => <div className="resume-card" key={`${snapshot.created_at ?? index}-${snapshot.resumed_from ?? 'resume'}`}><dl><dt>恢复节点</dt><dd>{snapshot.resumed_from || '未知节点'}</dd><dt>审核动作</dt><dd>{snapshot.action || 'approved'}</dd><dt>恢复结果</dt><dd>{snapshot.status || 'completed'}</dd></dl><div className="resume-block"><strong>恢复前 state</strong><StateItems value={snapshot.before_state} /></div><div className="resume-block"><strong>恢复后新增事件</strong>{snapshot.after_events?.length ? <ol>{snapshot.after_events.slice(0, 8).map((item, itemIndex) => <li key={`${item.event_id ?? itemIndex}-${itemIndex}`}><span>{item.node ?? item.type ?? 'event'}</span><em>{item.status ?? 'unknown'}</em><p>{item.content}</p></li>)}</ol> : <p className="empty-text">暂无新增事件快照</p>}</div></div>)}</div>;
}

export function RunOutputs({ toolCalls = [], agentOutputs = [] }: { toolCalls?: string[]; agentOutputs?: string[] }) {
  return <><OutputList title="工具调用" empty="暂无工具调用" items={toolCalls} /><OutputList title="Agent 输出" empty="暂无 Agent 输出" items={agentOutputs} /></>;
}

function StateItems({ value }: { value?: Record<string, unknown> }) { const items = value ? Object.entries(value).slice(0, 8).map(([key, item]) => `${key}: ${summarize(item)}`) : []; return items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p className="empty-text">暂无 state 快照</p>; }
function deriveSnapshots(events: AgentEvent[]): ResumeSnapshot[] { return events.filter((event) => event.type === 'resume' || event.data?.resume_snapshot).map((event) => (event.data?.resume_snapshot ?? event.data ?? {}) as ResumeSnapshot); }
function summarize(value: unknown) { if (typeof value === 'string') return value; try { return JSON.stringify(value, null, 2); } catch { return String(value); } }
