import type { AgentEvent } from '../types';

export function TaskTimeline({ events, selectedEventId, onSelect, empty = '运行任务后，这里会显示完整执行事件。' }: { events: AgentEvent[]; selectedEventId?: string; onSelect?: (event: AgentEvent) => void; empty?: string }) {
  if (!events.length) return <p className="empty-text">{empty}</p>;
  return <div className="timeline">{events.map((event, index) => <button type="button" className={`timeline-row ${selectedEventId === event.event_id ? 'selected' : ''}`} key={`${event.event_id ?? index}-${index}`} onClick={() => onSelect?.(event)}><div className={`dot ${event.status ?? 'running'}`} /><div><div className="event-main"><strong>{event.data?.node_name ? String(event.data.node_name) : event.node ?? event.type}</strong><span>{event.agent ?? 'runtime'}</span><em>{event.status}</em></div><p>{event.content}</p></div></button>)}</div>;
}
