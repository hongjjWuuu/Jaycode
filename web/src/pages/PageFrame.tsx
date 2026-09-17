import { ReactNode } from 'react';
import { PageBoundary } from '../components/PageBoundary';

export type WorkbenchPageProps = { children: ReactNode };

export function WorkbenchPageFrame({ name, children }: WorkbenchPageProps & { name: string }) {
  return <PageBoundary name={name}>{children}</PageBoundary>;
}
