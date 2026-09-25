import type { ComponentType, ReactNode } from 'react';
import { PageBoundary } from '../components/PageBoundary';
import type { ViewKey } from '../hooks/useViewNavigation';

const frame = (name: string) => ({ children }: { children: ReactNode }) => <PageBoundary name={name}>{children}</PageBoundary>;

export const pageFrames: Record<ViewKey, ComponentType<{ children: ReactNode }>> = {
  run: frame('run'), workflow: frame('workflow'), reports: frame('reports'), chat: frame('chat'), history: frame('history'), operations: frame('operations'), llm: frame('llm'), mcp: frame('mcp'), skills: frame('skills'), marketplace: frame('marketplace'), benchmark: frame('benchmark'),
};
