import type { MemoryRecord, RagDocument, RagGoldCase, RagResult } from '../types';
import { requestJson } from './http';

const json = (body: unknown): RequestInit => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
export async function queryKnowledge(collection: string, question: string, limit = 5): Promise<RagResult[]> { return (await requestJson<{ results?: RagResult[] }>('/api/v1/rag/query', json({ collection, question, limit }), 'Knowledge query failed')).results ?? []; }
export async function listKnowledgeDocuments(collection = ''): Promise<RagDocument[]> { return (await requestJson<{ documents?: RagDocument[] }>(`/api/v1/rag/documents${collection ? `?collection=${encodeURIComponent(collection)}` : ''}`, {}, 'Knowledge documents failed')).documents ?? []; }
export function addKnowledgeNote(collection: string, path: string, content: string) { return requestJson('/api/v1/knowledge/notes', json({ collection, path, content }), 'Knowledge note failed'); }
export async function listRagGoldCases(collection = '', includeDisabled = true): Promise<RagGoldCase[]> { const params = new URLSearchParams({ include_disabled: String(includeDisabled) }); if (collection) params.set('collection', collection); return (await requestJson<{ cases?: RagGoldCase[] }>(`/api/v1/rag/gold-cases?${params}`, {}, 'RAG Gold Set list failed')).cases ?? []; }
export async function saveRagGoldCase(payload: Partial<RagGoldCase> & { question: string; collection: string }): Promise<RagGoldCase> { return (await requestJson<{ case: RagGoldCase }>('/api/v1/rag/gold-cases', json(payload), 'RAG Gold Set save failed')).case; }
export function deleteRagGoldCase(caseId: string): Promise<void> { return requestJson<void>(`/api/v1/rag/gold-cases/${encodeURIComponent(caseId)}`, { method: 'DELETE' }, 'RAG Gold Set delete failed'); }
export function extractMemoryCandidates(payload: { text: string; scope?: string; scope_id?: string; source_type?: string; source_ref?: string }): Promise<MemoryRecord[]> { return requestJson('/api/v1/memories/extract', json(payload), 'Memory extraction failed'); }
export function listMemories(status = ''): Promise<MemoryRecord[]> { return requestJson(`/api/v1/memories${status ? `?status=${encodeURIComponent(status)}` : ''}`, {}, 'Memory list failed'); }
export function confirmMemory(memoryId: string): Promise<MemoryRecord> { return requestJson(`/api/v1/memories/${encodeURIComponent(memoryId)}/confirm`, json({}), 'Memory confirmation failed'); }
export function rejectMemory(memoryId: string): Promise<MemoryRecord> { return requestJson(`/api/v1/memories/${encodeURIComponent(memoryId)}/reject`, { method: 'POST' }, 'Memory rejection failed'); }
export function deleteMemory(memoryId: string): Promise<void> { return requestJson<void>(`/api/v1/memories/${encodeURIComponent(memoryId)}`, { method: 'DELETE' }, 'Memory deletion failed'); }
