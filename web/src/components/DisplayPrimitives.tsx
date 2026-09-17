import { ReactNode } from 'react';

export function PanelTitle({ icon, title, action }: { icon?: ReactNode; title: string; action?: ReactNode }) {
  return <div className="panel-title"><span>{icon}{title}</span>{action}</div>;
}

export function FieldHelp({ children }: { children: ReactNode }) {
  return <small className="field-help">{children}</small>;
}

export function EnabledState({ enabled, label = '状态' }: { enabled: boolean; label?: string }) {
  return <span className={`mcp-approval-state enabled-state ${enabled ? 'approved' : 'revoked'}`}>{label}: {enabled ? 'enabled' : 'disabled'}</span>;
}

export function RiskBadge({ level }: { level?: string }) {
  const value = (level || 'low').toLowerCase();
  return <span className={`risk-badge ${value}`}>risk: {value}</span>;
}
