"""Edit the Brand Knowledge Base: rules (versioned), approved facts (validity + supersession),
terminology, channel profiles and confidential terms, plus CSV import and export.

Only brand managers can edit. Every change bumps the rulebook or factbook version, which
invalidates cached reviews, and is recorded in the hash-chained audit log.
"""

import csv
import io
import json
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.auth import Permission, current_workspace_id, require
from app.db import get_session
from app.ml.embeddings import get_embedder
from app.models import (
    ConfidentialTerm,
    Fact,
    Rule,
    RuleStatus,
    Severity,
    Term,
    TermKind,
    User,
    Workspace,
)
from app.schemas.rulebook import (
    ChannelUpdate,
    ConfidentialIn,
    FactIn,
    FactUpdate,
    ImportResult,
    RuleIn,
    RuleOut,
    RuleUpdate,
    SupersedeIn,
    TermIn,
    TermOut,
)
from app.scoped import get_channel, get_fact
from app.visual.brand import DEFAULT_PALETTE

router = APIRouter(prefix="/api/rulebook", tags=["rulebook (edit)"])
editor = require(Permission.edit_rulebook)

MAX_CSV_BYTES = 1024 * 1024


def _bump(session: Session, ws: str, rulebook: bool = False, factbook: bool = False) -> None:
    workspace = session.get_one(Workspace, ws)
    if rulebook:
        workspace.rulebook_version += 1
    if factbook:
        workspace.factbook_version += 1


def _active_rule(session: Session, ws: str, code: str) -> Rule:
    rule = session.scalar(
        select(Rule)
        .where(Rule.workspace_id == ws, Rule.code == code, Rule.status == RuleStatus.active)
        .order_by(Rule.version.desc())
    )
    if rule is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No active rule {code}.")
    return rule


def _embed(statement: str) -> list[float] | None:
    embedder = get_embedder()
    return embedder.embed([statement])[0] if embedder else None


# --- rules -----------------------------------------------------------------------------


@router.post("/rules", response_model=RuleOut, status_code=201)
def create_rule(
    body: RuleIn, user: User = Depends(editor), session: Session = Depends(get_session)
) -> Rule:
    exists = select(Rule).where(Rule.workspace_id == user.workspace_id, Rule.code == body.code)
    if session.scalar(exists):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Rule {body.code} already exists.")
    rule = Rule(
        workspace_id=user.workspace_id,
        code=body.code,
        category=body.category,
        title=body.title,
        description=body.description,
        severity=Severity(body.severity),
        config=body.config,
        source_doc=body.source_doc,
        source_page=body.source_page,
        version=1,
        status=RuleStatus.active,
        created_by=user.id,
        approved_by=user.id,
    )
    session.add(rule)
    _bump(session, user.workspace_id, rulebook=True)
    session.flush()
    audit.record(session, "rule", body.code, "rule_created", user.id, body.model_dump())
    session.commit()
    return rule


@router.put("/rules/{code}", response_model=RuleOut)
def update_rule(
    code: str,
    body: RuleUpdate,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> Rule:
    """Edits never overwrite: the old version is retired and a new version is created."""
    current = _active_rule(session, user.workspace_id, code)
    current.status = RuleStatus.retired
    rule = Rule(
        workspace_id=user.workspace_id,
        code=code,
        category=current.category,
        title=body.title,
        description=body.description,
        severity=Severity(body.severity),
        config=body.config,
        source_doc=body.source_doc,
        source_page=body.source_page,
        version=current.version + 1,
        status=RuleStatus.active,
        created_by=user.id,
        approved_by=user.id,
    )
    session.add(rule)
    _bump(session, user.workspace_id, rulebook=True)
    session.flush()
    audit.record(
        session,
        "rule",
        code,
        "rule_updated",
        user.id,
        {"version": rule.version, **body.model_dump()},
    )
    session.commit()
    return rule


@router.delete("/rules/{code}", status_code=204)
def retire_rule(
    code: str, user: User = Depends(editor), session: Session = Depends(get_session)
) -> None:
    rule = _active_rule(session, user.workspace_id, code)
    rule.status = RuleStatus.retired
    _bump(session, user.workspace_id, rulebook=True)
    audit.record(session, "rule", code, "rule_retired", user.id, {"version": rule.version})
    session.commit()


@router.get("/rules/{code}/versions", response_model=list[RuleOut])
def rule_versions(
    code: str, ws: str = Depends(current_workspace_id), session: Session = Depends(get_session)
) -> list[Rule]:
    query = select(Rule).where(Rule.workspace_id == ws, Rule.code == code)
    return list(session.scalars(query.order_by(Rule.version.desc())))


# --- facts -----------------------------------------------------------------------------


def _fact(session: Session, ws: str, fact_id: str) -> Fact:
    fact = get_fact(session, ws, fact_id)
    if fact is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No fact {fact_id}.")
    return fact


@router.post("/facts", status_code=201)
def create_fact(
    body: FactIn, user: User = Depends(editor), session: Session = Depends(get_session)
) -> dict[str, str]:
    if get_fact(session, user.workspace_id, body.id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Fact {body.id} already exists.")
    session.add(
        Fact(
            workspace_id=user.workspace_id,
            **body.model_dump(),
            status=RuleStatus.active,
            embedding=_embed(body.statement),
            created_by=user.id,
            approved_by=user.id,
        )
    )
    _bump(session, user.workspace_id, factbook=True)
    session.flush()
    audit.record(session, "fact", body.id, "fact_created", user.id, body.model_dump(mode="json"))
    session.commit()
    return {"id": body.id}


@router.put("/facts/{fact_id}")
def update_fact(
    fact_id: str,
    body: FactUpdate,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    fact = _fact(session, user.workspace_id, fact_id)
    if fact.statement != body.statement:
        fact.embedding = _embed(body.statement)
    for key, value in body.model_dump().items():
        setattr(fact, key, value)
    fact.version += 1
    fact.approved_by = user.id
    _bump(session, user.workspace_id, factbook=True)
    audit.record(
        session,
        "fact",
        fact_id,
        "fact_updated",
        user.id,
        {"version": fact.version, **body.model_dump(mode="json")},
    )
    session.commit()
    return {"id": fact_id, "version": fact.version}


@router.post("/facts/{fact_id}/supersede", status_code=201)
def supersede_fact(
    fact_id: str,
    body: SupersedeIn,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    """Replace a fact with a new one from a date. Claims matching the old fact become
    'outdated' and point to the new fact."""
    old = _fact(session, user.workspace_id, fact_id)
    if old.superseded_by:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{fact_id} is already superseded by " f"{old.superseded_by}."
        )
    if get_fact(session, user.workspace_id, body.new_id):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Fact {body.new_id} already exists.")
    session.add(
        Fact(
            workspace_id=user.workspace_id,
            id=body.new_id,
            statement=body.statement,
            source_doc=body.source_doc,
            source_page=body.source_page,
            valid_from=body.valid_from,
            status=RuleStatus.active,
            embedding=_embed(body.statement),
            created_by=user.id,
            approved_by=user.id,
        )
    )
    old.superseded_by = body.new_id
    old.valid_until = body.valid_from - timedelta(days=1)
    _bump(session, user.workspace_id, factbook=True)
    session.flush()
    audit.record(
        session,
        "fact",
        fact_id,
        "fact_superseded",
        user.id,
        {"by": body.new_id, "statement": body.statement, "valid_from": body.valid_from.isoformat()},
    )
    session.commit()
    return {"id": body.new_id, "supersedes": fact_id}


@router.delete("/facts/{fact_id}", status_code=204)
def retire_fact(
    fact_id: str, user: User = Depends(editor), session: Session = Depends(get_session)
) -> None:
    fact = _fact(session, user.workspace_id, fact_id)
    fact.status = RuleStatus.retired
    _bump(session, user.workspace_id, factbook=True)
    audit.record(session, "fact", fact_id, "fact_retired", user.id, {})
    session.commit()


# --- terms, channels, confidential terms ----------------------------------------------


@router.post("/terms", response_model=TermOut, status_code=201)
def create_term(
    body: TermIn, user: User = Depends(editor), session: Session = Depends(get_session)
) -> Term:
    term = Term(
        workspace_id=user.workspace_id, **{**body.model_dump(), "kind": TermKind(body.kind)}
    )
    session.add(term)
    _bump(session, user.workspace_id, rulebook=True)
    session.flush()
    audit.record(session, "term", str(term.id), "term_created", user.id, body.model_dump())
    session.commit()
    return term


@router.put("/terms/{term_id}", response_model=TermOut)
def update_term(
    term_id: int,
    body: TermIn,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> Term:
    term = session.get(Term, term_id)
    if term is None or term.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Term not found.")
    for key, value in {**body.model_dump(), "kind": TermKind(body.kind)}.items():
        setattr(term, key, value)
    _bump(session, user.workspace_id, rulebook=True)
    audit.record(session, "term", str(term_id), "term_updated", user.id, body.model_dump())
    session.commit()
    return term


@router.delete("/terms/{term_id}", status_code=204)
def delete_term(
    term_id: int, user: User = Depends(editor), session: Session = Depends(get_session)
) -> None:
    term = session.get(Term, term_id)
    if term is None or term.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Term not found.")
    audit.record(session, "term", str(term_id), "term_deleted", user.id, {"term": term.term})
    session.delete(term)
    _bump(session, user.workspace_id, rulebook=True)
    session.commit()


@router.put("/channels/{channel_id}")
def update_channel(
    channel_id: str,
    body: ChannelUpdate,
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    channel = get_channel(session, user.workspace_id, channel_id)
    if channel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Channel not found.")
    for key, value in body.model_dump().items():
        setattr(channel, key, value)
    _bump(session, user.workspace_id, rulebook=True)
    audit.record(session, "channel", channel_id, "channel_updated", user.id, body.model_dump())
    session.commit()
    return {"id": channel_id}


@router.post("/confidential", status_code=201)
def add_confidential(
    body: ConfidentialIn, user: User = Depends(editor), session: Session = Depends(get_session)
) -> dict[str, int]:
    term = ConfidentialTerm(workspace_id=user.workspace_id, **body.model_dump())
    session.add(term)
    session.flush()
    # The term itself is confidential: the audit log records only that one was added.
    audit.record(
        session, "confidential", str(term.id), "confidential_added", user.id, {"kind": body.kind}
    )
    session.commit()
    return {"id": term.id}


@router.delete("/confidential/{term_id}", status_code=204)
def delete_confidential(
    term_id: int, user: User = Depends(editor), session: Session = Depends(get_session)
) -> None:
    term = session.get(ConfidentialTerm, term_id)
    if term is None or term.workspace_id != user.workspace_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Term not found.")
    session.delete(term)
    audit.record(session, "confidential", str(term_id), "confidential_removed", user.id, {})
    session.commit()


# --- CSV export and import -------------------------------------------------------------

RULE_COLUMNS = [
    "id",
    "category",
    "title",
    "description",
    "severity",
    "config",
    "source_doc",
    "source_page",
    "version",
    "status",
]
FACT_COLUMNS = [
    "id",
    "statement",
    "source_doc",
    "source_page",
    "valid_from",
    "valid_until",
    "superseded_by",
]
TERM_COLUMNS = ["term", "kind", "variants", "replacement", "case_sensitive", "rule_id", "note"]


def _csv_response(name: str, columns: list[str], rows: list[dict[str, Any]]) -> Response:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="paywise_{name}.csv"'},
    )


@router.get("/export/{kind}.csv")
def export_csv(
    kind: str, ws: str = Depends(current_workspace_id), session: Session = Depends(get_session)
) -> Response:
    if kind == "rules":
        rules = session.scalars(
            select(Rule)
            .where(Rule.workspace_id == ws, Rule.status == RuleStatus.active)
            .order_by(Rule.code)
        )
        return _csv_response(
            kind,
            RULE_COLUMNS,
            [
                {
                    "id": r.code,
                    "category": r.category,
                    "title": r.title,
                    "description": r.description,
                    "severity": r.severity.value,
                    "config": json.dumps(r.config),
                    "source_doc": r.source_doc,
                    "source_page": r.source_page or "",
                    "version": r.version,
                    "status": r.status.value,
                }
                for r in rules
            ],
        )
    if kind == "facts":
        facts = session.scalars(
            select(Fact)
            .where(Fact.workspace_id == ws, Fact.status == RuleStatus.active)
            .order_by(Fact.id)
        )
        return _csv_response(
            kind,
            FACT_COLUMNS,
            [
                {
                    "id": f.id,
                    "statement": f.statement,
                    "source_doc": f.source_doc,
                    "source_page": f.source_page or "",
                    "valid_from": f.valid_from or "",
                    "valid_until": f.valid_until or "",
                    "superseded_by": f.superseded_by or "",
                }
                for f in facts
            ],
        )
    if kind == "terms":
        terms = session.scalars(
            select(Term).where(Term.workspace_id == ws).order_by(Term.kind, Term.term)
        )
        return _csv_response(
            kind,
            TERM_COLUMNS,
            [
                {
                    "term": t.term,
                    "kind": t.kind.value,
                    "variants": "|".join(t.variants),
                    "replacement": t.replacement or "",
                    "case_sensitive": str(t.case_sensitive).lower(),
                    "rule_id": t.rule_code,
                    "note": t.note,
                }
                for t in terms
            ],
        )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Export rules, facts or terms.")


def _opt_int(value: str) -> int | None:
    return int(value) if value.strip() else None


@router.post("/import/{kind}", response_model=ImportResult)
async def import_csv(
    kind: str,
    file: UploadFile = File(...),
    user: User = Depends(editor),
    session: Session = Depends(get_session),
) -> ImportResult:
    data = await file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "CSV files must be under 1 MB.")
    try:
        rows = list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, "Upload a UTF-8 CSV file."
        ) from exc
    result = ImportResult(created=0, updated=0, unchanged=0, errors=[])
    for number, raw_row in enumerate(rows, start=2):
        row = {k: (v or "") for k, v in raw_row.items() if k is not None}
        try:
            if kind == "rules":
                outcome = _import_rule(session, row, user)
            elif kind == "facts":
                outcome = _import_fact(session, row, user)
            elif kind == "terms":
                outcome = _import_term(session, row, user)
            else:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "Import rules, facts or terms.")
        except (
            KeyError,
            ValueError,
            TypeError,
            AttributeError,
            ValidationError,
            json.JSONDecodeError,
        ) as exc:
            result.errors.append(f"Row {number}: {type(exc).__name__}: {str(exc)[:120]}")
            continue
        setattr(result, outcome, getattr(result, outcome) + 1)
    if result.created or result.updated:
        _bump(session, user.workspace_id, rulebook=kind != "facts", factbook=kind == "facts")
        audit.record(
            session,
            kind,
            f"import:{kind}",
            f"{kind}_imported",
            user.id,
            result.model_dump(exclude={"errors"}),
        )
    session.commit()
    return result


def _import_rule(session: Session, row: dict[str, str], user: User) -> str:
    body = RuleIn(
        code=row["id"],
        category=row["category"],
        title=row["title"],
        description=row["description"],
        severity=row["severity"],
        config=json.loads(row.get("config") or "{}"),
        source_doc=row["source_doc"],
        source_page=_opt_int(row.get("source_page", "")),
    )
    current = session.scalar(
        select(Rule).where(
            Rule.workspace_id == user.workspace_id,
            Rule.code == body.code,
            Rule.status == RuleStatus.active,
        )
    )
    if current is None:
        session.add(
            Rule(
                workspace_id=user.workspace_id,
                code=body.code,
                category=body.category,
                title=body.title,
                description=body.description,
                severity=Severity(body.severity),
                config=body.config,
                source_doc=body.source_doc,
                source_page=body.source_page,
                version=1,
                status=RuleStatus.active,
                created_by=user.id,
                approved_by=user.id,
            )
        )
        return "created"
    same = (
        current.title,
        current.description,
        current.severity.value,
        current.config,
        current.source_doc,
        current.source_page,
    ) == (
        body.title,
        body.description,
        body.severity,
        body.config,
        body.source_doc,
        body.source_page,
    )
    if same:
        return "unchanged"
    current.status = RuleStatus.retired
    session.add(
        Rule(
            workspace_id=user.workspace_id,
            code=body.code,
            category=current.category,
            title=body.title,
            description=body.description,
            severity=Severity(body.severity),
            config=body.config,
            source_doc=body.source_doc,
            source_page=body.source_page,
            version=current.version + 1,
            status=RuleStatus.active,
            created_by=user.id,
            approved_by=user.id,
        )
    )
    session.flush()
    return "updated"


def _import_fact(session: Session, row: dict[str, str], user: User) -> str:
    body = FactIn(
        id=row["id"],
        statement=row["statement"],
        source_doc=row["source_doc"],
        source_page=_opt_int(row.get("source_page", "")),
        valid_from=row.get("valid_from") or None,
        valid_until=row.get("valid_until") or None,
    )
    fact = get_fact(session, user.workspace_id, body.id)
    if fact is None:
        session.add(
            Fact(
                workspace_id=user.workspace_id,
                **body.model_dump(),
                status=RuleStatus.active,
                superseded_by=row.get("superseded_by") or None,
                embedding=_embed(body.statement),
                created_by=user.id,
                approved_by=user.id,
            )
        )
        return "created"
    if (fact.statement, fact.valid_from, fact.valid_until) == (
        body.statement,
        body.valid_from,
        body.valid_until,
    ):
        return "unchanged"
    if fact.statement != body.statement:
        fact.embedding = _embed(body.statement)
    for key, value in body.model_dump(exclude={"id"}).items():
        setattr(fact, key, value)
    fact.version += 1
    return "updated"


def _import_term(session: Session, row: dict[str, str], user: User) -> str:
    body = TermIn(
        term=row["term"],
        kind=row["kind"],
        variants=[v for v in row.get("variants", "").split("|") if v],
        replacement=row.get("replacement") or None,
        case_sensitive=row.get("case_sensitive", "").lower() == "true",
        rule_code=row["rule_id"],
        note=row.get("note", ""),
    )
    term = session.scalar(
        select(Term).where(
            Term.workspace_id == user.workspace_id,
            Term.term == body.term,
            Term.kind == TermKind(body.kind),
        )
    )
    values = {**body.model_dump(), "kind": TermKind(body.kind)}
    if term is None:
        session.add(Term(workspace_id=user.workspace_id, **values))
        return "created"
    if all(getattr(term, k) == v for k, v in values.items()):
        return "unchanged"
    for key, value in values.items():
        setattr(term, key, value)
    return "updated"


# --- brand palette ---------------------------------------------------------------------


class PaletteColour(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    hex: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class PaletteIn(BaseModel):
    colours: list[PaletteColour] = Field(min_length=1, max_length=16)


@router.get("/palette", response_model=list[PaletteColour])
def get_palette(
    ws: str = Depends(current_workspace_id), session: Session = Depends(get_session)
) -> list[dict[str, str]]:
    """The brand colours visuals are checked against (VIS-01)."""
    workspace = session.get_one(Workspace, ws)
    return list(workspace.settings.get("brand_palette") or DEFAULT_PALETTE)


@router.put("/palette", response_model=list[PaletteColour])
def set_palette(
    body: PaletteIn, user: User = Depends(editor), session: Session = Depends(get_session)
) -> list[dict[str, str]]:
    workspace = session.get_one(Workspace, user.workspace_id)
    colours = [{"name": c.name.strip(), "hex": c.hex.upper()} for c in body.colours]
    workspace.settings = {**workspace.settings, "brand_palette": colours}
    _bump(session, user.workspace_id, rulebook=True)
    audit.record(
        session, "workspace", workspace.id, "palette_updated", user.id, {"colours": colours}
    )
    session.commit()
    return colours
