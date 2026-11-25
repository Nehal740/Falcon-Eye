
from sqlalchemy.orm import Session

from models import FirewallEvent, ApprovalRequest


def create_firewall_event(db: Session, event_data: dict):
    event = FirewallEvent(**event_data)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def create_approval(db: Session, approval_data: dict):
    approval = ApprovalRequest(**approval_data)
    db.add(approval)
    db.commit()
    db.refresh(approval)
    return approval


def get_all_events(db: Session):
    return db.query(FirewallEvent).all()


def get_pending_approvals(db: Session):
    return db.query(ApprovalRequest).filter(
        ApprovalRequest.status == "PENDING"
    ).all()


def get_all_approvals(db: Session):
    return db.query(ApprovalRequest).all()



def decide_approval(db: Session, approval_id: str, decision: str):
    approval = db.query(ApprovalRequest).filter(
        ApprovalRequest.approval_id == approval_id
    ).first()

    if approval is None or approval.status != "PENDING":
        return None

    approval.status = decision
    db.commit()
    db.refresh(approval)

    return approval
