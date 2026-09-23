import { X } from 'lucide-react';
import { useState } from 'react';
import { FieldHelp } from '../DisplayPrimitives';

export type FocusKind = 'module' | 'file';

type Props = {
  error: string;
  files: string[];
  loading: boolean;
  modules: string[];
  onClose: () => void;
  onSelect: (kind: FocusKind, value: string) => void;
};

export function FocusPicker({ error, files, loading, modules, onClose, onSelect }: Props) {
  const [kind, setKind] = useState<FocusKind>('module');
  const [keyword, setKeyword] = useState('');
  const normalizedKeyword = keyword.trim().toLowerCase();
  const moduleItems = modules.filter((item) => item.toLowerCase().includes(normalizedKeyword)).slice(0, 80);
  const fileItems = files.filter((item) => !normalizedKeyword || item.toLowerCase().includes(normalizedKeyword)).slice(0, 160);
  const items = kind === 'module' ? moduleItems : fileItems;

  return <div className="modal-backdrop"><div className="focus-modal"><div className="modal-title"><strong>选择聚焦范围</strong><button className="icon-button" onClick={onClose}><X size={15} /></button></div><div className="focus-tabs"><button className={kind === 'module' ? 'active' : ''} onClick={() => setKind('module')}>模块</button><button className={kind === 'file' ? 'active' : ''} onClick={() => setKind('file')}>文件</button></div><input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索模块或文件" /><FieldHelp>输入模块名、目录名或文件名关键字，用来缩小聚焦分析范围。</FieldHelp>{loading ? <p className="empty-text">正在扫描项目文件...</p> : null}{error ? <p className="error-text">{error}</p> : null}<div className="focus-list">{items.map((item) => <button key={`${kind}-${item}`} onClick={() => onSelect(kind, item)}><span>{item}</span><small>{kind === 'module' ? '只分析该模块目录' : '只读取并分析该文件'}</small></button>)}{!loading && !items.length ? <p className="empty-text">没有匹配结果</p> : null}</div></div></div>;
}
