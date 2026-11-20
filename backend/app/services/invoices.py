"""centrix can approve repair costs up to and including EUR 3,000."""
from app.db import now_iso
from app.services.cases import record_event
from app.states import CaseStatus


CENTRIX_LIMIT_CENTS = 300_000


def review_legacy_invoices(conn):
    # P0 closed even large invoices automatically. Preserve its original closure event.
    affected = conn.execute(
        "SELECT c.id FROM cases c JOIN case_documents d ON c.id=d.case_id "
        "WHERE c.status=? AND d.kind='invoice' AND json_extract(d.content,'$.currency')='EUR' "
        "AND json_extract(d.content,'$.amount_cents')>? "
        "AND NOT EXISTS (SELECT 1 FROM case_events e WHERE e.case_id=c.id AND e.type='invoice.manager_approved')",
        (CaseStatus.CLOSED, CENTRIX_LIMIT_CENTS)).fetchall()
    for case in affected:
        target = CaseStatus.AWAITING_INVOICE_APPROVAL
        conn.execute("UPDATE cases SET status=?,updated_at=? WHERE id=?", (target, now_iso(), case["id"]))
        record_event(conn, case["id"], "case.status_changed", "system:migration", {
            "from": CaseStatus.CLOSED, "to": target, "reason": "existing invoice exceeds centrix approval limit"})
