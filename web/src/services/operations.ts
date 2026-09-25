import type { OperationsOverview } from '../types';
import { requestJson } from './http';

export function getOperationsOverview(): Promise<OperationsOverview> {
  return requestJson('/api/v1/operations/overview', {}, '运营状态读取失败');
}
