import { PanelTitle } from './DisplayPrimitives';

/** Shared task-result list used by the run workspace without coupling it to the app shell. */
export function OutputList({ title, empty, items }: { title: string; empty: string; items: string[] }) {
  return <div className="output-list"><PanelTitle title={title} />{items.length ? items.map((item) => <p key={item}>{item}</p>) : <p className="empty-text">{empty}</p>}</div>;
}
