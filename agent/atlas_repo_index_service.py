from __future__ import annotations
import ast, fnmatch, hashlib, json, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from agent.atlas_repo_index_schema import *
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage
from agent.atlas_repo_index_policies import POLICIES

class AtlasRepoIndexService:
    def __init__(self,data_root:Path):
        self.storage=AtlasRepoIndexStorage(data_root)
    def _resolve_project_root(self,p:str)->Path:
        root=Path(p).expanduser().resolve()
        if not p.strip() or not root.exists() or not root.is_dir(): raise ValueError('project_path must be an existing directory')
        return root
    def build_or_update(self,request:AtlasRepoIndexRequest)->AtlasRepoIndexResult:
        root=self._resolve_project_root(request.project_path)
        pol=POLICIES.get(request.policy_id,POLICIES['repo_index_v1'])
        if request.mode=='status_only':
            latest=self.storage.load_json(str(root),'latest.json');
            return AtlasRepoIndexResult(**latest) if latest else AtlasRepoIndexResult(workspace_id=request.workspace_id,project_path=str(root),index_run_id='repoindex_none',policy_id=request.policy_id,status='status_only',mode=request.mode,created_at=datetime.now(timezone.utc).isoformat())
        files=[]
        for p in root.rglob('*'):
            if p.is_symlink() or not p.is_file(): continue
            rel=p.relative_to(root).as_posix()
            if any(part in set(pol.get('exclude_dirs',[])) for part in p.parts): continue
            if request.include_globs and not any(fnmatch.fnmatch(rel,g) for g in request.include_globs): continue
            if any(fnmatch.fnmatch(rel,g) for g in request.exclude_globs): continue
            if p.suffix.lower() not in set(pol.get('supported_extensions',[])): continue
            files.append(p)
            if len(files)>=min(request.max_files,pol.get('max_files',5000)): break
        symbols=[]; edges=[]; skipped=[]; warnings=[]
        for p in files:
            b=p.read_bytes(); rel=p.relative_to(root).as_posix()
            if len(b)>min(request.max_file_bytes,pol.get('max_file_bytes',1_000_000)) or b'\x00' in b: skipped.append(rel); continue
            txt=b.decode('utf-8',errors='ignore')
            if p.suffix=='.py':
                try:
                    t=ast.parse(txt)
                    for n in ast.walk(t):
                        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                            k='class' if isinstance(n,ast.ClassDef) else 'function'
                            symbols.append(AtlasRepoSymbol(symbol_id=f'{rel}:{n.lineno}:{getattr(n,"name","")}',name=getattr(n,'name',''),kind=k,file_path=rel,language='python',line_start=n.lineno,line_end=getattr(n,'end_lineno',n.lineno),docstring=ast.get_docstring(n) or ''))
                        if isinstance(n,ast.Import):
                            for a in n.names: edges.append(AtlasRepoDependencyEdge(source=rel,target=a.name,edge_type='import',confidence='medium'))
                        if isinstance(n,ast.ImportFrom):
                            edges.append(AtlasRepoDependencyEdge(source=rel,target=(n.module or ''),edge_type='relative_import' if n.level else 'import',confidence='high' if n.level else 'medium'))
                except SyntaxError:
                    warnings.append(f'syntax error skipped: {rel}')
            if p.suffix.lower() in {'.js','.ts','.tsx','.jsx'}:
                for m in re.finditer(r'function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*)',txt):
                    n=next(g for g in m.groups() if g)
                    symbols.append(AtlasRepoSymbol(symbol_id=f'{rel}:{n}:{m.start()}',name=n,kind='function',file_path=rel,language='javascript'))
                for m in re.finditer(r"import\s+.+?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)",txt):
                    t=m.group(1) or m.group(2); edges.append(AtlasRepoDependencyEdge(source=rel,target=t,edge_type='import',confidence='medium'))
                for m in re.finditer(r"fetch\(['\"](/api/[^'\"]+)['\"]",txt): edges.append(AtlasRepoDependencyEdge(source=rel,target=m.group(1),edge_type='api_call',confidence='medium'))
            if p.suffix.lower()=='.html':
                for m in re.finditer(r'<script[^>]*src=["\']([^"\']+)',txt): edges.append(AtlasRepoDependencyEdge(source=rel,target=m.group(1),edge_type='route',confidence='medium'))
        reverse={}
        for e in edges: reverse.setdefault(e.target,[]).append(e.source)
        changed=request.changed_files or [f.relative_to(root).as_posix() for f in files]
        impacted=sorted(set(changed+[s for c in changed for s in reverse.get(c,[]) ]))
        related=sorted([f for f in impacted if f.startswith('tests/') or '/test_' in f or f.endswith('_test.py')])
        idx='repoindex_'+uuid.uuid4().hex[:8]
        result=AtlasRepoIndexResult(workspace_id=request.workspace_id,project_path=str(root),index_run_id=idx,policy_id=request.policy_id,status='indexed' if not skipped else 'partial',mode=request.mode,total_files=len(files),indexed_files=len(files)-len(skipped),skipped_files=len(skipped),changed_files=changed,impacted_files=impacted,related_tests=related,symbol_count=len(symbols),edge_count=len(edges),created_at=datetime.now(timezone.utc).isoformat(),warnings=warnings,artifact_paths={})
        payload=result.model_dump()
        d=self.storage.dir_for(str(root))
        for name,obj in [('symbols.json',[s.model_dump() for s in symbols]),('files.json',{}),('dependency_graph.json',{'nodes':list({e.source for e in edges}|{e.target for e in edges}),'edges':[e.model_dump() for e in edges]}),('reverse_dependency_graph.json',reverse),('related_tests.json',{'related_tests':related}),('manifest.json',{'project_path':str(root),'project_hash':self.storage.project_hash(str(root)),'index_run_id':idx,'created_at':result.created_at,'total_files':result.total_files,'indexed_files':result.indexed_files,'symbol_count':result.symbol_count,'edge_count':result.edge_count,'file_hashes':[]}), (f'{idx}.json',payload),('latest.json',payload)]:
            self.storage.save_json(str(root),name,obj)
        (d/f'{idx}.md').write_text(f"# Atlas Repo Index\n\n## Summary\n- index_run_id: {idx}\n- project_path: {root}\n- status: {result.status}\n- total_files: {result.total_files}\n- indexed_files: {result.indexed_files}\n- skipped_files: {result.skipped_files}\n- symbol_count: {result.symbol_count}\n- edge_count: {result.edge_count}\n\n## Safety\n- shell executed: false\n- remote git executed: false\n- files modified: false\n",encoding='utf-8')
        return result
    def load_latest(self,workspace_id:str,project_path:str)->dict: return self.storage.load_json(str(self._resolve_project_root(project_path)),'latest.json')
    def query_impacts(self,project_path:str,changed_files:list[str])->dict:
        latest=self.load_latest('default',project_path)
        if not changed_files: return latest
        impacted=sorted(set(changed_files+latest.get('impacted_files',[])))
        return {'impacted_files':impacted,'impacted_symbols':latest.get('impacted_symbols',[]),'related_tests':latest.get('related_tests',[])}
    def query_related_tests(self,project_path:str,changed_files:list[str])->dict:
        latest=self.load_latest('default',project_path)
        return {'related_tests':latest.get('related_tests',[]),'changed_files':changed_files}
