import { WorkspaceComposition } from './WorkspaceComposition';

/**
 * Application-shell boundary. Domain state and page composition live below
 * this entry so App and URL navigation stay independent from feature state.
 */
export function WorkspaceRuntime() {
  return <WorkspaceComposition />;
}
