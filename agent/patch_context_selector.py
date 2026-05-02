from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass
class PatchContextCandidate:
    candidate_id: str
    target_file: str
    start_line: int
    end_line: int
    text: str
    score: float
    reason: str


class PatchContextSelector:
    def _tokens(self, text: str) -> list[str]:
        toks = [t for t in re.split(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", text or "") if len(t) >= 2]
        return toks[:40]

    def select_candidates(self, file_content: str, step_title: str, step_description: str, max_candidates: int = 5, target_file: str = "") -> list[PatchContextCandidate]:
        lines = file_content.splitlines()
        if not lines:
            return [PatchContextCandidate("cand_1", target_file, 1, 1, file_content, 0.1, "empty file fallback")]
        if len(lines) <= 40:
            return [PatchContextCandidate("cand_1", target_file, 1, len(lines), file_content, 0.6, "short file whole-content candidate")]

        tokens = self._tokens(step_title + " " + step_description)
        scored=[]
        for i,l in enumerate(lines, start=1):
            lo=l.lower(); score=0.0; reasons=[]
            for t in tokens:
                if t.lower() in lo:
                    score += 1.0; reasons.append(f"keyword:{t}")
            if any(x in lo for x in ["def ", "class ", "function", "todo", "fixme", "patch", "verify", "replace"]):
                score += 0.4; reasons.append("code-marker")
            if score>0:
                s=max(1,i-20); e=min(len(lines),i+20)
                scored.append((score,s,e,", ".join(reasons[:3]) or "keyword match"))
        if not scored:
            scored=[(0.2,1,min(40,len(lines)),"fallback head"),(0.2,max(1,len(lines)-39),len(lines),"fallback tail")]
        scored.sort(key=lambda x:x[0], reverse=True)
        out=[]; used=set()
        for score,s,e,r in scored:
            key=(s,e)
            if key in used: continue
            used.add(key)
            txt="\n".join(lines[s-1:e])
            out.append(PatchContextCandidate(f"cand_{len(out)+1}", target_file, s,e,txt,float(score),r))
            if len(out)>=max_candidates: break
        return out
