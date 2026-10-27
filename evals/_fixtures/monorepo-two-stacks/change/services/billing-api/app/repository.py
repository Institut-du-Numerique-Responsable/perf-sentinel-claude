from sqlalchemy import text
from sqlalchemy.orm import Session


class InvoiceRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, invoice_id: int):
        row = self.session.execute(
            text("SELECT id, number FROM invoice WHERE id = :id"), {"id": invoice_id}
        ).first()
        return {"id": row.id, "number": row.number} if row else None

    def list_for_client(self, client_id: int):
        ids = self.session.execute(
            text("SELECT id FROM invoice WHERE client_id = :c"), {"c": client_id}
        ).scalars()
        return [self.get(invoice_id) for invoice_id in ids]
