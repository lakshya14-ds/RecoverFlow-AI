import sys
sys.path.insert(0, '/home/ec2-user/RecoverFlow-AI')
from dotenv import load_dotenv
load_dotenv('/home/ec2-user/RecoverFlow-AI/.env')
from app.database.db_manager import SessionLocal
from app.database import models
s = SessionLocal()
deleted = s.query(models.EvidenceSegment).filter_by(evidence_id=54).delete()
s.commit()
print(f"deleted {deleted} segments for evidence 54 from RDS PostgreSQL")
