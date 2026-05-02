from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PatchQualityResult:
    quality_score: float
    warnings: list[str]
    summary: str


class PatchQualityEvaluator:
    def evaluate(self, proposal, file_content: str, step_title: str, step_description: str) -> PatchQualityResult:
        score = 0.8
        warns=[]
        o=(getattr(proposal,'original_block','') or '').strip()
        r=(getattr(proposal,'replacement_block','') or '').strip()
        if len(o.splitlines()) < 1 or len(o) < 3:
            score -= 0.25; warns.append('original_block too short')
        if len(o.splitlines()) > 80:
            score -= 0.2; warns.append('original_block too long')
        if len(r.encode('utf-8')) > 8000:
            score -= 0.2; warns.append('replacement_block is large')
        cid = ((getattr(proposal,'metadata',{}) or {}).get('candidate_id') or '').strip()
        if not cid:
            score -= 0.1; warns.append('candidate_id missing')
        conf=((getattr(proposal,'metadata',{}) or {}).get('llm_confidence'))
        if isinstance(conf,(int,float)) and conf < 0.4:
            score -= 0.1; warns.append('low llm confidence')
        if r.startswith('#') or r.startswith('//'):
            score -= 0.15; warns.append('replacement may be comment-only')
        if o and r and o.strip()==r.strip():
            score -= 0.2; warns.append('replacement is effectively no-op')
        text=(step_title+' '+step_description).lower()
        if text and o and not any(tok in o.lower() or tok in r.lower() for tok in text.split()[:5] if len(tok)>=3):
            score -= 0.1; warns.append('weak step relevance')
        score=max(0.0,min(1.0,score))
        band='good' if score>=0.7 else ('review carefully' if score>=0.4 else 'poor')
        return PatchQualityResult(score,warns,f'quality={band} score={score:.2f}')
