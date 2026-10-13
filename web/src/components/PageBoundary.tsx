import { ReactNode } from 'react';

/** Stable page boundary used by the workbench views while their internals evolve independently. */
export function PageBoundary({ name, children }: { name: string; children: ReactNode }) {
  return <div className="page-boundary" data-page={name}>{children}</div>;
}
