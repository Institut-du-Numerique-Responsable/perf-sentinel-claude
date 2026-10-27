from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.db import get_session
from app.repository import InvoiceRepository

app = FastAPI()


@app.get("/invoices/{invoice_id}")
def get_invoice(invoice_id: int, session: Session = Depends(get_session)):
    return InvoiceRepository(session).get(invoice_id)
