"""Report exports (Phase 4, Part D). CSV for every report type plus a
minimal stdlib PDF renderer (Helvetica text tables, no dependency).
Read-only; gov endpoints only."""

import csv
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.execution import ImplementationUpdate
from app.models.government import GovernmentAction
from app.models.problem import Problem
from app.models.solution import Solution
from app.services import analytics_service


def _cell(value) -> str:
    if value is None:
        return ""
    text = str(value)
    return text.replace("\r", " ").replace("\n", " ")


def to_csv(headers: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([_cell(v) for v in row])
    return buf.getvalue().encode("utf-8")


def to_pdf(title: str, headers: list[str], rows: list[list]) -> bytes:
    """Minimal valid PDF: title + monospace-ish Helvetica lines, paginated
    at 44 lines per page. No dependency."""
    lines = [title, ""]
    col_widths = [max([len(h)] + [len(_cell(r[i])) for r in rows])
                    for i, h in enumerate(headers)]
    col_widths = [min(w, 28) for w in col_widths]

    def fmt(row):
        return " | ".join(_cell(v)[:w].ljust(w)
                          for v, w in zip(row, col_widths))

    lines.append(fmt(headers))
    lines.append("-" * min(sum(col_widths) + 3 * (len(headers) - 1), 110))
    for row in rows:
        lines.append(fmt(row))

    pages: list[list[str]] = []
    for i in range(0, max(len(lines), 1), 44):
        pages.append(lines[i:i + 44] or [""])

    objects: list[bytes] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{3 + i * 2} 0 R" for i in range(len(pages)))
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    for page_lines in pages:
        text = "".join(
            f"BT /F1 9 Tf 36 {760 - n * 14} Td ({_pdf_escape(line)}) Tj ET\n"
            for n, line in enumerate(page_lines))
        stream = f"<< /Length {len(text.encode())} >>\nstream\n{text}endstream".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {len(objects) + 2} 0 R /Resources << /Font << /F1 "
            f"{len(objects) + 3} 0 R >> >> >>".encode())
        objects.append(stream)
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref_at = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref_at}\n%%EOF".encode())
    return out.getvalue()


def _pdf_escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace("(", "\\(")
                .replace(")", "\\)"))[:110]


def complaint_rows(db: Session) -> tuple[list[str], list[list]]:
    from app.services import government_review_service

    headers = ["ticket", "title", "category", "location", "severity",
               "status", "resolution", "decided_at", "created_at"]
    rows = []
    for p in db.execute(select(Problem).order_by(
            Problem.created_at.desc()).limit(1000)).scalars().all():
        review = government_review_service.get_for_problem(db, p.id)
        resolution = (government_review_service.resolution_type_for(
            review.status) if review else None)
        if resolution is None and p.status in (
                "OPEN", "COLLABORATION", "IN_DEVELOPMENT", "PILOT",
                "IMPLEMENTED"):
            resolution = "PUBLIC"
        rows.append([p.ticket, p.title, p.category, p.location, p.severity,
                     p.status, resolution or "",
                     review.decided_at if review else "", p.created_at])
    return headers, rows


def implementation_rows(db: Session) -> tuple[list[str], list[list]]:
    headers = ["ticket", "stage", "title", "created_at"]
    rows = []
    for u in db.execute(select(ImplementationUpdate).order_by(
            ImplementationUpdate.created_at.desc()).limit(1000)).scalars().all():
        problem = db.get(Problem, u.problem_id)
        rows.append([problem.ticket if problem else "?",
                     u.stage, u.title, u.created_at])
    return headers, rows


def solution_rows(db: Session) -> tuple[list[str], list[list]]:
    headers = ["ticket", "problem", "title", "status", "review_status",
               "selected", "created_at"]
    rows = []
    for s in db.execute(select(Solution).order_by(
            Solution.created_at.desc()).limit(1000)).scalars().all():
        problem = db.get(Problem, s.problem_id)
        rows.append([s.ticket, problem.ticket if problem else "?",
                     s.title, s.status, s.review_status,
                     "yes" if s.is_selected else "no", s.created_at])
    return headers, rows


def audit_rows(db: Session, *, official=None, action=None, ticket=None,
               date_from=None, date_to=None, limit=1000) -> tuple[list[str], list[list]]:
    from app.services import government_review_service

    query = select(GovernmentAction).order_by(
        GovernmentAction.created_at.desc())
    if action:
        query = query.where(GovernmentAction.action == action)
    if ticket:
        query = query.where(GovernmentAction.ticket == ticket.strip())
    if date_from:
        query = query.where(GovernmentAction.created_at >= date_from)
    if date_to:
        query = query.where(GovernmentAction.created_at <= date_to)
    rows = []
    for a in db.execute(query.limit(max(limit, 1))).scalars().all():
        if official:
            actor = government_review_service.get_actor(db, a.actor_id)
            label = ""
            if actor is not None:
                label = getattr(actor, "employee_id", "") or ""
            if official.strip().lower() not in label.lower():
                continue
        rows.append([a.ticket, a.action, a.previous_status or "",
                     a.new_status, a.actor_type or "",
                     a.reason or "", a.created_at])
    headers = ["ticket", "action", "previous_status", "new_status",
               "actor_type", "reason", "created_at"]
    return headers, rows
