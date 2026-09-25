import { useCallback, useEffect, useState } from 'react';

export const viewKeys = [
  'run', 'workflow', 'reports', 'chat', 'history', 'operations', 'llm', 'mcp', 'skills', 'marketplace', 'benchmark',
] as const;

export type ViewKey = typeof viewKeys[number];

function viewFromLocation(): ViewKey {
  const requested = new URLSearchParams(window.location.search).get('view');
  return viewKeys.includes(requested as ViewKey) ? requested as ViewKey : 'run';
}

/** Synchronizes the existing activeView navigation with a shareable URL, without a router. */
export function useViewNavigation() {
  const [activeView, setActiveViewState] = useState<ViewKey>(viewFromLocation);

  useEffect(() => {
    const onPopState = () => setActiveViewState(viewFromLocation());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  const setActiveView = useCallback((view: ViewKey) => {
    const url = new URL(window.location.href);
    url.searchParams.set('view', view);
    window.history.pushState({ view }, '', `${url.pathname}${url.search}${url.hash}`);
    setActiveViewState(view);
  }, []);

  return { activeView, setActiveView };
}
