from __future__ import annotations
import hashlib, json
from pathlib import Path

class AtlasRepoIndexStorage:
    def __init__(self,data_root:Path):
        self.base=Path(data_root)/'atlas'/'repo_index'
    def project_hash(self,project_path:str)->str:
        return hashlib.sha256(project_path.encode()).hexdigest()[:16]
    def dir_for(self,project_path:str)->Path:
        d=self.base/self.project_hash(project_path); d.mkdir(parents=True,exist_ok=True); return d
    def save_json(self,project_path:str,name:str,payload:dict):
        p=self.dir_for(project_path)/name; p.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8'); return str(p)
    def load_json(self,project_path:str,name:str)->dict:
        p=self.dir_for(project_path)/name
        return json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
