"""Intent and Delivery trace projector (PDT-4).

Projects delivery traceability from canonical Atlas systems into the twin as a
reference/relation model:

    Conversation -> Message -> Requirement -> PlanItem -> File/Symbol -> Test -> Evidence

The twin stores normalized references (IDs) and relationships, never replacing the
authoritative stores (conversation storage, PlanPool/workflow storage, verification
storage). The projector is a pure `IntentTracePort.project` implementation: it takes an
`IntentDeliveryEvent` and returns a `TwinDelta`. Missing links produce diagnostics rather
than fabricated edges.

Node ids reuse the same deterministic hash as the static graph so intent edges can target
structural file/symbol nodes (cross-domain links) by canonical ref.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agent.project_twin.contracts import IntentDeliveryEvent, TwinDelta, TwinEdge, TwinNode
from agent.project_twin.static_graph import nid

PROJECTOR_VERSION = "intent_trace.v1"

_DOMAIN = "intent_delivery"


class _Builder:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.now = datetime.now(timezone.utc)
        self.nodes: list[TwinNode] = []
        self.edges: list[TwinEdge] = []
        self.diagnostics: list[dict] = []
        self._seen_n: set[str] = set()
        self._seen_e: set[str] = set()

    def node(self, *, node_type: str, canonical_ref: str, label: str, source_ref: str,
             properties: dict | None = None, confidence: float = 1.0) -> str:
        node_id = nid(canonical_ref)
        if canonical_ref not in self._seen_n:
            self._seen_n.add(canonical_ref)
            self.nodes.append(
                TwinNode(
                    node_id=node_id, project_id=self.project_id, domain=_DOMAIN,
                    node_type=node_type, canonical_ref=canonical_ref, label=label,
                    properties=properties or {}, source_kind="atlas", source_ref=source_ref,
                    derivation="canonical_projection", confidence=confidence, status="declared",
                    valid_from=self.now, created_at=self.now, updated_at=self.now,
                )
            )
        return node_id

    def edge(self, *, edge_type: str, source_ref: str, target_ref: str, evidence_source: str,
             confidence: float = 1.0) -> None:
        edge_id = nid(f"{edge_type}|{source_ref}|{target_ref}")
        if edge_id in self._seen_e:
            return
        self._seen_e.add(edge_id)
        self.edges.append(
            TwinEdge(
                edge_id=edge_id, project_id=self.project_id, domain=_DOMAIN,
                source_node_id=nid(source_ref), target_node_id=nid(target_ref),
                edge_type=edge_type, source_kind="atlas", source_ref=evidence_source,
                derivation="canonical_projection", confidence=confidence, status="declared",
                valid_from=self.now, created_at=self.now, updated_at=self.now,
            )
        )

    def missing(self, code: str, **detail: Any) -> None:
        self.diagnostics.append({"code": code, **detail})


def _conv_ref(cid: str) -> str:
    return f"conversation://{cid}"


def _msg_ref(cid: str, mid: str) -> str:
    return f"message://{cid}/{mid}"


def _req_ref(rid: str) -> str:
    return f"requirement://{rid}"


def _planitem_ref(pool: str, item: str) -> str:
    return f"planitem://{pool}/{item}"


class IntentDeliveryProjector:
    """Pure `IntentTracePort` implementation."""

    def project(self, event: IntentDeliveryEvent) -> TwinDelta:
        b = _Builder(event.project_id)
        payload = event.payload or {}
        handler = {
            "conversation.message.completed": self._message,
            "requirement.confirmed": self._requirement,
            "plan_item.completed": self._plan_item,
            "safe_apply.completed": self._apply,
            "verification.completed": self._verification,
        }.get(event.event_type)

        if handler is None:
            b.missing("unsupported_event_type", event_type=event.event_type)
        else:
            handler(b, payload, event.source_ref or event.event_type)

        return TwinDelta(
            project_id=event.project_id,
            idempotency_key=event.idempotency_key,
            trigger_type=event.event_type,
            trigger_ref=event.source_ref,
            nodes=b.nodes,
            edges=b.edges,
            diagnostics=b.diagnostics,
        )

    # -- handlers -------------------------------------------------------------

    @staticmethod
    def _message(b: _Builder, p: dict, src: str) -> None:
        cid = p.get("conversation_id")
        mid = p.get("message_id")
        if not cid or not mid:
            b.missing("missing_message_ids", conversation_id=cid, message_id=mid)
            return
        b.node(node_type="conversation", canonical_ref=_conv_ref(cid), label=f"conversation {cid}", source_ref=cid)
        b.node(node_type="message", canonical_ref=_msg_ref(cid, mid), label=p.get("summary", f"message {mid}"),
               source_ref=f"{cid}/{mid}", properties={"role": p.get("role")})
        b.edge(edge_type="contains_message", source_ref=_conv_ref(cid), target_ref=_msg_ref(cid, mid), evidence_source=src)

    @staticmethod
    def _requirement(b: _Builder, p: dict, src: str) -> None:
        rid = p.get("requirement_id")
        if not rid:
            b.missing("missing_requirement_id")
            return
        b.node(node_type="requirement", canonical_ref=_req_ref(rid), label=p.get("text", f"requirement {rid}"), source_ref=rid)
        cid = p.get("source_conversation_id")
        mid = p.get("source_message_id")
        if cid and mid:
            b.edge(edge_type="derives_requirement", source_ref=_msg_ref(cid, mid), target_ref=_req_ref(rid), evidence_source=src)
        else:
            b.missing("requirement_without_source_message", requirement_id=rid)
        for c in p.get("constraints", []) or []:
            cidc = c.get("id")
            if not cidc:
                continue
            cref = f"constraint://{rid}/{cidc}"
            b.node(node_type="constraint", canonical_ref=cref, label=c.get("text", f"constraint {cidc}"), source_ref=f"{rid}/{cidc}")
            b.edge(edge_type="has_constraint", source_ref=_req_ref(rid), target_ref=cref, evidence_source=src)

    @staticmethod
    def _plan_item(b: _Builder, p: dict, src: str) -> None:
        pool = p.get("plan_pool_id")
        item = p.get("plan_item_id")
        if not pool or not item:
            b.missing("missing_plan_item_ids", plan_pool_id=pool, plan_item_id=item)
            return
        b.node(node_type="plan", canonical_ref=f"plan://{pool}", label=f"plan {pool}", source_ref=pool)
        pi_ref = _planitem_ref(pool, item)
        b.node(node_type="plan_item", canonical_ref=pi_ref, label=p.get("summary", f"plan item {item}"), source_ref=f"{pool}/{item}")
        b.edge(edge_type="contains_item", source_ref=f"plan://{pool}", target_ref=pi_ref, evidence_source=src)

        rid = p.get("requirement_id")
        if rid:
            b.edge(edge_type="planned_as", source_ref=_req_ref(rid), target_ref=pi_ref, evidence_source=src)
        else:
            b.missing("plan_item_without_requirement", plan_item_id=item)

        for f in p.get("changed_files", []) or []:
            b.edge(edge_type="changed_file", source_ref=pi_ref, target_ref=f"file://{f}", evidence_source=src)
        for sym in p.get("changed_symbols", []) or []:
            # symbols are passed as canonical refs (e.g. py://rel#qual)
            b.edge(edge_type="changed_symbol", source_ref=pi_ref, target_ref=sym, evidence_source=src)

    @staticmethod
    def _apply(b: _Builder, p: dict, src: str) -> None:
        proposal = p.get("proposal_id")
        pool = p.get("plan_pool_id")
        item = p.get("plan_item_id")
        if not proposal:
            b.missing("missing_proposal_id")
            return
        pref = f"proposal://{proposal}"
        b.node(node_type="proposal", canonical_ref=pref, label=f"proposal {proposal}", source_ref=proposal,
               properties={"apply_status": p.get("apply_status")})
        if pool and item:
            b.edge(edge_type="produced_proposal", source_ref=_planitem_ref(pool, item), target_ref=pref, evidence_source=src)
        run = p.get("run_id")
        if run:
            rref = f"run://{run}"
            b.node(node_type="run", canonical_ref=rref, label=f"run {run}", source_ref=run)
            b.edge(edge_type="executed_in", source_ref=pref, target_ref=rref, evidence_source=src)
        for f in p.get("applied_files", []) or []:
            b.edge(edge_type="applied_to", source_ref=pref, target_ref=f"file://{f}", evidence_source=src)

    @staticmethod
    def _verification(b: _Builder, p: dict, src: str) -> None:
        vid = p.get("verification_id")
        pool = p.get("plan_pool_id")
        item = p.get("plan_item_id")
        if not vid:
            b.missing("missing_verification_id")
            return
        vref = f"verification://{vid}"
        b.node(node_type="verification", canonical_ref=vref, label=f"verification {vid}", source_ref=vid,
               properties={"result": p.get("result")})
        if pool and item:
            b.edge(edge_type="verified_by", source_ref=_planitem_ref(pool, item), target_ref=vref, evidence_source=src)
        else:
            b.missing("verification_without_plan_item", verification_id=vid)

        for t in p.get("tests", []) or []:
            tref = t.get("ref")
            if not tref:
                continue
            # reuse the structural test:// canonical ref so this links to PDT-3 test nodes
            b.edge(edge_type="ran_test", source_ref=vref, target_ref=tref, evidence_source=src,
                   confidence=1.0 if t.get("result") in {"passed", "failed"} else 0.6)
        for ev in p.get("evidence", []) or []:
            eid = ev.get("id")
            if not eid:
                continue
            eref = f"evidence://{eid}"
            b.node(node_type="evidence", canonical_ref=eref, label=ev.get("summary", f"evidence {eid}"),
                   source_ref=eid, properties={"result": ev.get("result")})
            # link evidence to the test it came from when known, else to the verification
            origin = ev.get("test_ref") or vref
            b.edge(edge_type="produced_evidence", source_ref=origin, target_ref=eref, evidence_source=src)
