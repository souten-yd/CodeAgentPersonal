from __future__ import annotations
import ast, fnmatch, hashlib, re, uuid
from datetime import datetime, timezone
from pathlib import Path
from agent.atlas_repo_index_schema import *
from agent.atlas_repo_index_storage import AtlasRepoIndexStorage
from agent.atlas_repo_index_policies import POLICIES

class ProjectIntelligenceRepoIndexService:
    def __init__(self,data_root:Path): self.storage=AtlasRepoIndexStorage(data_root)
    def _resolve_project_root(self,p:str)->Path:
        root=Path(p).expanduser().resolve()
        if not p.strip() or not root.exists() or not root.is_dir(): raise ValueError('project_path must be an existing directory')
        return root
    def _hash(self,b:bytes)->str: return hashlib.sha256(b).hexdigest()
    def _resolve_target(self,root:Path,src:str,tgt:str)->tuple[str,str]:
        sp=(root/src).parent
        if tgt.startswith('./') or tgt.startswith('../'):
            for ex in ('','.py','.js','.ts','.tsx','.jsx'):
                c=(sp/(tgt+ex)).resolve()
                if c.exists() and c.is_file(): return c.relative_to(root).as_posix(),'high'
        if tgt.startswith('/static/js/'):
            c=(root/'web/js'/tgt.split('/static/js/',1)[1]).resolve()
            if c.exists(): return c.relative_to(root).as_posix(),'high'
        if re.match(r'^[a-zA-Z_][\w\.]*$',tgt):
            c=(root/(tgt.replace('.','/')+'.py')).resolve()
            if c.exists(): return c.relative_to(root).as_posix(),'high'
        return tgt,'medium'
    def build_or_update(self,request:AtlasRepoIndexRequest)->AtlasRepoIndexResult:
        root=self._resolve_project_root(request.project_path); pol=POLICIES.get(request.policy_id,POLICIES['repo_index_v1'])
        if request.mode=='status_only':
            latest=self.storage.load_json(str(root),'latest.json')
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
        latest=self.storage.load_json(str(root),'latest.json') or {}
        prev_files=self.storage.load_json(str(root),'files.json') or {}
        prev_edges=self.storage.load_json(str(root),'dependency_graph.json').get('edges',[]) if self.storage.load_json(str(root),'dependency_graph.json') else []
        prev_hash={x.get('file_path'):x for x in self.storage.load_json(str(root),'manifest.json').get('file_hashes',[])}
        changed_hint=set(request.changed_files or [])
        file_nodes={}; symbols=[]; edges=[]; skipped=[]; warnings=[]; hash_rows=[]; reparsed=[]; reused=[]
        for p in files:
            b=p.read_bytes(); rel=p.relative_to(root).as_posix(); m=p.stat().st_mtime_ns; sz=len(b); h=self._hash(b)
            hash_rows.append({'file_path':rel,'sha256':h,'mtime_ns':m,'size_bytes':sz})
            if len(b)>min(request.max_file_bytes,pol.get('max_file_bytes',1_000_000)) or b'\x00' in b: skipped.append(rel); continue
            is_changed=(rel in changed_hint) if changed_hint else (prev_hash.get(rel,{}).get('sha256')!=h)
            if request.incremental and not request.force_rebuild and prev_files.get(rel) and not is_changed:
                file_nodes[rel]=prev_files[rel]; reused.append(rel); continue
            reparsed.append(rel)
            txt=b.decode('utf-8',errors='ignore'); imports=[]; routes=[]; tests=[]; fsyms=[]
            if p.suffix=='.py':
                try:
                    t=ast.parse(txt)
                    for n in ast.walk(t):
                        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
                            k='class' if isinstance(n,ast.ClassDef) else 'function'; nm=getattr(n,'name','')
                            s=AtlasRepoSymbol(symbol_id=f'{rel}:{n.lineno}:{nm}',name=nm,kind=k,file_path=rel,language='python',line_start=n.lineno,line_end=getattr(n,'end_lineno',n.lineno),docstring=ast.get_docstring(n) or '')
                            symbols.append(s); fsyms.append(s.model_dump())
                        if isinstance(n,ast.Import):
                            for a in n.names: imports.append(a.name)
                        if isinstance(n,ast.ImportFrom):
                            mod=(('.'*n.level)+(n.module or '')) if n.level else (n.module or '')
                            imports.append(mod)
                except SyntaxError: warnings.append(f'syntax error skipped: {rel}')
            if p.suffix.lower() in {'.js','.ts','.tsx','.jsx'}:
                for mth in re.finditer(r'function\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)|const\s+([A-Za-z_$][\w$]*)',txt):
                    nm=next(g for g in mth.groups() if g); s=AtlasRepoSymbol(symbol_id=f'{rel}:{nm}:{mth.start()}',name=nm,kind='function',file_path=rel,language='javascript'); symbols.append(s); fsyms.append(s.model_dump())
                for mth in re.finditer(r"import\s+.+?from\s+['\"]([^'\"]+)['\"]|require\(['\"]([^'\"]+)['\"]\)",txt): imports.append(mth.group(1) or mth.group(2))
                for mth in re.finditer(r"fetch\(['\"](/api/[^'\"]+)['\"]",txt): routes.append(mth.group(1))
            if p.suffix.lower()=='.html':
                for mth in re.finditer(r'<script[^>]*src=["\']([^"\']+)',txt): imports.append(mth.group(1))
            for imp in imports:
                tgt,cf=self._resolve_target(root,rel,imp); edges.append(AtlasRepoDependencyEdge(source=rel,target=tgt,edge_type='import',confidence=cf))
            for rt in routes: edges.append(AtlasRepoDependencyEdge(source=rel,target=rt,edge_type='api_call',confidence='medium'))
            if rel.startswith('tests/') or '/test_' in rel or rel.endswith('_test.py'): tests.append(rel)
            file_nodes[rel]={'file_path':rel,'language':p.suffix.lstrip('.'),'size_bytes':sz,'mtime_ns':m,'sha256':h,'symbols':fsyms,'imports':imports,'imported_by':[],'routes':routes,'tests':tests,'metadata':{}}
        deleted=[x for x in prev_files.keys() if x not in file_nodes]
        if request.incremental and not request.force_rebuild:
            for e in prev_edges:
                if e.get('source') in reused and e not in [x.model_dump() for x in edges]: edges.append(AtlasRepoDependencyEdge(**e))
            for k,v in prev_files.items():
                if k in reused and k not in file_nodes: file_nodes[k]=v
        reverse={}
        for e in edges: reverse.setdefault(e.target,[]).append(e.source)
        for k,v in file_nodes.items(): v['imported_by']=sorted(set(reverse.get(k,[])))
        changed=sorted(set(changed_hint or reparsed+deleted))
        impacted=sorted(set(changed+[s for c in changed for s in reverse.get(c,[])]))
        related=sorted(set([f for f in file_nodes if f.startswith('tests/') and any((Path(f).stem.replace('test_','') in c or Path(c).stem in f) for c in changed)] + [f for f in impacted if f.startswith('tests/') or '/test_' in f or f.endswith('_test.py')]))
        idx='repoindex_'+uuid.uuid4().hex[:8]
        result=AtlasRepoIndexResult(workspace_id=request.workspace_id,project_path=str(root),index_run_id=idx,policy_id=request.policy_id,status='indexed' if not skipped else 'partial',mode=request.mode,total_files=len(files),indexed_files=len(files)-len(skipped),skipped_files=len(skipped),changed_files=changed,impacted_files=impacted,related_tests=related,symbol_count=len(symbols),edge_count=len(edges),created_at=datetime.now(timezone.utc).isoformat(),warnings=warnings,artifact_paths={},metadata={'incremental_used':bool(request.incremental and not request.force_rebuild and len(reused)>0),'reused_files':len(reused),'reparsed_files':len(reparsed),'deleted_files':len(deleted)})
        payload=result.model_dump(); graph={'nodes':list({e.source for e in edges}|{e.target for e in edges}),'edges':[e.model_dump() for e in edges]}
        self.storage.save_json(str(root),'symbols.json',[s.model_dump() for s in symbols]); self.storage.save_json(str(root),'files.json',file_nodes)
        self.storage.save_json(str(root),'dependency_graph.json',graph); self.storage.save_json(str(root),'reverse_dependency_graph.json',reverse)
        related_map={c:{'tests':[t for t in related if Path(c).stem in t or Path(t).stem.replace('test_','') in c],'confidence':'medium','reasons':['basename_match_or_impact']} for c in changed}
        self.storage.save_json(str(root),'related_tests.json',{'related_tests':related,'by_changed_file':related_map})
        self.storage.save_json(str(root),'manifest.json',{'project_path':str(root),'project_hash':self.storage.project_hash(str(root)),'index_run_id':idx,'created_at':result.created_at,'total_files':result.total_files,'indexed_files':result.indexed_files,'symbol_count':result.symbol_count,'edge_count':result.edge_count,'file_hashes':hash_rows})
        self.storage.save_json(str(root),f'{idx}.json',payload); self.storage.save_json(str(root),'latest.json',payload)
        return result
    def load_latest(self,workspace_id:str,project_path:str)->dict: return self.storage.load_json(str(self._resolve_project_root(project_path)),'latest.json')
    def query_impacts(self,project_path:str,changed_files:list[str])->dict:
        latest=self.load_latest('default',project_path); changed=changed_files or latest.get('changed_files',[])
        impacted=sorted(set(changed+latest.get('impacted_files',[])))
        return {'impacted_files':impacted,'related_tests':latest.get('related_tests',[])}
    def query_related_tests(self,project_path:str,changed_files:list[str])->dict:
        root=self._resolve_project_root(project_path); data=self.storage.load_json(str(root),'related_tests.json')
        return {'related_tests':data.get('related_tests',[]),'by_changed_file':data.get('by_changed_file',{}),'changed_files':changed_files}


class ProjectIntelligenceRepoIndexAdapter:
    """Compatibility adapter for Atlas repository-index API routes."""

    def __init__(self, data_root: str | Path) -> None:
        self.data_root = Path(data_root)
        self._service = ProjectIntelligenceRepoIndexService(self.data_root)
        self._storage = AtlasRepoIndexStorage(self.data_root)

    def policies(self) -> dict:
        return {"policies": POLICIES}

    def build_or_update(self, request: AtlasRepoIndexRequest):
        return self._service.build_or_update(request)

    def query_impacts(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.query_impacts(request.project_path, request.changed_files)

    def query_related_tests(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.query_related_tests(request.project_path, request.changed_files)

    def load_latest(self, request: AtlasRepoIndexRequest) -> dict:
        return self._service.load_latest(request.workspace_id, request.project_path)

    def load_result_by_hash(self, project_hash: str, index_run_id: str) -> dict:
        return self._storage.load_result_by_hash(project_hash, index_run_id)
