import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import { useViewNavigation } from './useViewNavigation';

describe('useViewNavigation', () => {
  beforeEach(() => window.history.replaceState({}, '', '/?view=reports'));

  it('initializes from the view query and updates the URL', () => {
    const { result } = renderHook(() => useViewNavigation());
    expect(result.current.activeView).toBe('reports');

    act(() => result.current.setActiveView('chat'));
    expect(result.current.activeView).toBe('chat');
    expect(new URLSearchParams(window.location.search).get('view')).toBe('chat');
  });

  it('follows browser history navigation', () => {
    const { result } = renderHook(() => useViewNavigation());
    act(() => {
      window.history.pushState({}, '', '/?view=history');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });
    expect(result.current.activeView).toBe('history');
  });
});
