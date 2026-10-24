"""Seed the hero case for RecoverFlow hackathon demonstration.

Case Profile:
- Invoice Total: INR 2,40,000 (24,000,000 cents)
- Received:      INR 1,50,000 (15,000,000 cents) via verified ledger entry
- Outstanding:   INR 90,000 (9,000,000 cents)
- Disputed:      INR 30,000 (3,000,000 cents) line item delivery shortfall
- Undisputed:    INR 60,000 (6,000,000 cents) owed and actionable
"""
import sys
from datetime import date, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import models
from app.database.db_manager import SessionLocal, init_db
from app.services.receivables import split_balance
from scripts.generate_hero_pdfs import create_simple_pdf


def seed_hero_case() -> models.Invoice:
    init_db()
    
    # Ensure physical evidence PDF files exist on disk
    if not Path("docs/invoices/INV-2026-HERO.pdf").exists():
        create_simple_pdf(
            "docs/invoices/INV-2026-HERO.pdf",
            "COMMERCIAL TAX INVOICE - INV-2026-HERO",
            [
                "Invoice Number: INV-2026-HERO",
                "Date: 2026-09-09 | Due Date: 2026-10-09",
                "Customer: Apex Enterprises Pvt Ltd",
                "GSTIN: 27AABCA1234D1Z8",
                "----------------------------------------------------------------------",
                "Item: Precision Valve Sets (SKU: PVS-100)",
                "Quantity: 80 Units",
                "Unit Price: INR 3,000.00",
                "----------------------------------------------------------------------",
                "Subtotal: INR 2,40,000.00",
                "Total Invoiced Amount: INR 2,40,000.00",
                "Payment Terms: Net 30 Days via RTGS / Bank Transfer"
            ]
        )
    if not Path("docs/po/PO-2026-HERO.pdf").exists():
        create_simple_pdf(
            "docs/po/PO-2026-HERO.pdf",
            "PURCHASE ORDER - PO-2026-HERO",
            [
                "PO Reference: PO-2026-HERO",
                "PO Date: 2026-09-01",
                "Buyer: Apex Enterprises Pvt Ltd (Procurement Dept)",
                "Delivery Location: Warehouse Unit 4, Industrial Area Phase II",
                "----------------------------------------------------------------------",
                "Authorized Items:",
                "- 80 Units x Precision Valve Sets @ INR 3,000.00 = INR 2,40,000.00",
                "Payment Terms: Net 30 Days from invoice date",
                "Authorized Signature: Procurement Manager, Apex Enterprises Pvt Ltd"
            ]
        )

    db = SessionLocal()
    tenant_id = "local"
    inv_num = "INV-2026-HERO"

    try:
        # Check if hero case already exists; if so clean it up for idempotent re-seeding
        existing = db.query(models.Invoice).filter_by(tenant_id=tenant_id, invoice_number=inv_num).first()
        if existing:
            inv_id = existing.id
            proposals = db.query(models.AgentProposal).filter_by(tenant_id=tenant_id, invoice_id=inv_id).all()
            for p in proposals:
                db.query(models.ProposalDraftVersion).filter_by(tenant_id=tenant_id, proposal_id=p.id).delete()
                db.query(models.AgentCaseNote).filter_by(tenant_id=tenant_id, proposal_id=p.id).delete()
                db.query(models.AgentExecution).filter_by(tenant_id=tenant_id, proposal_id=p.id).delete()
            db.query(models.AgentProposal).filter_by(tenant_id=tenant_id, invoice_id=inv_id).delete()
            db.query(models.CaseEvidence).filter_by(tenant_id=tenant_id, invoice_id=inv_id).delete()
            db.query(models.CustomerMessage).filter_by(tenant_id=tenant_id, invoice_id=inv_id).delete()
            db.query(models.ReceivableEntry).filter_by(tenant_id=tenant_id, invoice_id=inv_id).delete()
            db.query(models.DunningCampaign).filter_by(tenant_id=tenant_id, invoice_id=inv_id).delete()
            db.delete(existing)
            db.commit()

        # 1. Create Counterparty
        counterparty = db.query(models.Counterparty).filter_by(tenant_id=tenant_id, tax_id="27AABCA1234F1Z5").first()
        if not counterparty:
            counterparty = models.Counterparty(
                tenant_id=tenant_id,
                name="Apex Enterprises Pvt Ltd",
                type="customer",
                email="procurement@apexenterprises.in",
                phone="+91 98200 12345",
                tax_id="27AABCA1234F1Z5",
                payment_terms=30,
                credit_limit=500000.00,
            )
            db.add(counterparty)
            db.flush()

        # 2. Create the Hero Invoice: INR 2,40,000
        hero_invoice = models.Invoice(
            tenant_id=tenant_id,
            invoice_number=inv_num,
            invoice_type="AR",
            counterparty_name="Apex Enterprises Pvt Ltd",
            counterparty_email="procurement@apexenterprises.in",
            counterparty_phone="+91 98200 12345",
            counterparty_tax_id="27AABCA1234F1Z5",
            issue_date=date.today() - timedelta(days=45),
            due_date=date.today() - timedelta(days=15),
            amount=240000.00,
            total_amount=240000.00,
            face_amount_cents=24000000,
            currency="INR",
            status="disputed",
            po_number="PO-2026-HERO",
            description="Commercial shipment: 80 units precision industrial valve sets @ INR 3,000/unit",
            dispute_open=True,
            disputed_cents=3000000,  # INR 30,000
            contact_suppressed=False,
            requires_human_review=False,
            source="manual",
        )
        db.add(hero_invoice)
        db.flush()
        hero_id = hero_invoice.id

        # 3. Create Received Payment Entry: INR 1,50,000
        payment_entry = models.ReceivableEntry(
            tenant_id=tenant_id,
            invoice_id=hero_id,
            kind="payment",
            amount_cents=-15000000,  # Negative in ledger for credit
            currency="INR",
            source="bank_feed",
            reference="UTR-AXIS-20261015-99214",
            actor="bank_reconciliation",
            note="Verified RTGS credit received against delivered units (50 units @ INR 3,000)",
        )
        db.add(payment_entry)

        # 4. Create Inbound Customer Reply detailing the dispute
        reply_message = models.CustomerMessage(
            tenant_id=tenant_id,
            invoice_id=hero_id,
            category="dispute",
            body=(
                "Regarding invoice INV-2026-HERO: We transferred INR 1,50,000 via RTGS. "
                "However, we dispute INR 30,000 because 10 valve sets were never delivered to our warehouse. "
                "The remaining undisputed balance of INR 60,000 will be remitted as soon as the delivery "
                "shortfall is adjusted."
            ),
            actor="procurement@apexenterprises.in",
            is_injection=False,
        )
        db.add(reply_message)

        # 5. Add Clickable Evidence Items
        evidence_items = [
            models.CaseEvidence(
                tenant_id=tenant_id,
                invoice_id=hero_id,
                claim_type="invoice_total",
                title="Billed Invoice Document (INV-2026-HERO)",
                description="Commercial Tax Invoice billed for 80 valve units @ INR 3,000 each = INR 2,40,000 total.",
                source_type="invoice_pdf",
                source_reference="docs/invoices/INV-2026-HERO.pdf",
                source_snippet="Line 1: 80x Precision Valve Sets @ INR 3,000.00 = Total INR 2,40,000.00",
                amount_cents=24000000,
                verified=True,
            ),
            models.CaseEvidence(
                tenant_id=tenant_id,
                invoice_id=hero_id,
                claim_type="purchase_order",
                title="Customer Purchase Order (PO-2026-HERO)",
                description="Purchase order authorizing purchase of 80 valve units under standard net 30 day terms.",
                source_type="po_document",
                source_reference="docs/po/PO-2026-HERO.pdf",
                source_snippet="PO Ref: PO-2026-HERO | Quantity: 80 Units | Net 30 Terms",
                amount_cents=24000000,
                verified=True,
            ),
            models.CaseEvidence(
                tenant_id=tenant_id,
                invoice_id=hero_id,
                claim_type="received_payment",
                title="Bank Payment Receipt (RTGS UTR-AXIS-20261015-99214)",
                description="Bank RTGS credit of INR 1,50,000 received on Oct 15 and matched to invoice.",
                source_type="bank_receipt",
                source_reference="BANK-RTGS-99214",
                source_snippet="CR UTR-AXIS-20261015-99214 INR 1,50,000.00 from Apex Enterprises Pvt Ltd",
                amount_cents=15000000,
                verified=True,
            ),
            models.CaseEvidence(
                tenant_id=tenant_id,
                invoice_id=hero_id,
                claim_type="dispute_item",
                title="Delivery Shortfall Dispute (Customer Thread)",
                description="Customer documented delivery shortfall of 10 valve units @ INR 3,000 each = INR 30,000 disputed balance.",
                source_type="customer_email",
                source_reference="EMAIL-THREAD-HERO-001",
                source_snippet="Dispute item: 10 units @ INR 3,000.00 shortfall. Disputed balance = INR 30,000.00",
                amount_cents=3000000,
                verified=True,
            ),
            models.CaseEvidence(
                tenant_id=tenant_id,
                invoice_id=hero_id,
                claim_type="undisputed_balance",
                title="Calculated Undisputed Balance",
                description="Deterministic balance calculation: Outstanding (INR 90,000) minus Disputed (INR 30,000) = INR 60,000 undisputed.",
                source_type="reconciliation_math",
                source_reference="LEDGER-REC-HERO",
                source_snippet="Total: INR 2,40,000 | Received: INR 1,50,000 | Outstanding: INR 90,000 | Disputed: INR 30,000 | Undisputed: INR 60,000",
                amount_cents=6000000,
                verified=True,
            ),
        ]
        db.add_all(evidence_items)

        # Audit Event
        db.add(models.AuditEvent(
            tenant_id=tenant_id,
            actor="hero_seed_script",
            action="hero_case_seeded",
            entity_type="invoice",
            entity_id=str(hero_id),
            details="Seeded hero case INV-2026-HERO: 2.40L total, 1.50L paid, 30k disputed, 60k undisputed",
        ))

        db.commit()
        db.refresh(hero_invoice)

        split = split_balance(db, hero_invoice)
        print("=" * 65)
        print("RECOVERFLOW HERO CASE SEEDED SUCCESSFULLY")
        print("=" * 65)
        print(f"Invoice ID:       {hero_invoice.id}")
        print(f"Invoice Number:   {hero_invoice.invoice_number}")
        print(f"Customer:         {hero_invoice.counterparty_name}")
        print(f"Status:           {hero_invoice.status}")
        print("-" * 65)
        print(f"1. Total Invoiced:  INR {split['invoice_total']:>12,.2f}  ({split['invoice_total_cents']} cents)")
        print(f"2. Received:        INR {split['received']:>12,.2f}  ({split['received_cents']} cents)")
        print(f"3. Outstanding:     INR {split['outstanding']:>12,.2f}  ({split['outstanding_cents']} cents)")
        print(f"4. Disputed:        INR {split['disputed']:>12,.2f}  ({split['disputed_cents']} cents)")
        print(f"5. Undisputed:      INR {split['undisputed']:>12,.2f}  ({split['undisputed_cents']} cents)")
        print("-" * 65)
        print(f"Evidence Items:   {len(evidence_items)} linked evidence sources")
        for ev in evidence_items:
            amt_str = f" [INR {ev.amount_cents / 100:,.2f}]" if ev.amount_cents else ""
            print(f"  * [{ev.source_type}] {ev.title}{amt_str}")
            print(f"    Source: {ev.source_reference}")
            print(f"    Snippet: \"{ev.source_snippet}\"")
        print("=" * 65)
        return hero_invoice
    finally:
        db.close()


if __name__ == "__main__":
    seed_hero_case()
