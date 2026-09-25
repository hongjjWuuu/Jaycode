import { WorkspaceRuntime } from './WorkspaceRuntime';

/** Stable workbench entry point; routing and runtime composition stay local. */
export function WorkspaceApp() {
  return <WorkspaceRuntime />;
}
