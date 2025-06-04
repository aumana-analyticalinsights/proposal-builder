# File: utils/history_manager.py

import json
import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from models.core_models import ProposalHistory, ProposalStatus

logger = logging.getLogger(__name__)

class HistoryManager:
    """Manages proposal history and metrics"""
    
    def __init__(self, db_path: str = "./history/proposals.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_database()
    
    def _initialize_database(self):
        """Initialize SQLite database for history storage"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS proposals (
                        id TEXT PRIMARY KEY,
                        job_title TEXT NOT NULL,
                        client_name TEXT,
                        generated_at TIMESTAMP NOT NULL,
                        status TEXT NOT NULL,
                        budget_proposed REAL NOT NULL,
                        final_cost REAL,
                        notes TEXT,
                        proposal_text TEXT,
                        execution_plan_json TEXT,
                        quality_score REAL,
                        win_probability REAL
                    )
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_generated_at 
                    ON proposals(generated_at)
                ''')
                
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_status 
                    ON proposals(status)
                ''')
                
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    def save_proposal(self, history: ProposalHistory, proposal_output=None) -> bool:
        """Save proposal to history"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO proposals 
                    (id, job_title, client_name, generated_at, status, 
                     budget_proposed, final_cost, notes, proposal_text,
                     execution_plan_json, quality_score, win_probability)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    history.id,
                    history.job_title,
                    history.client_name,
                    history.generated_at.isoformat(),
                    history.status.value,
                    history.budget_proposed,
                    history.final_cost,
                    history.notes,
                    proposal_output.proposal_text if proposal_output else None,
                    json.dumps(proposal_output.execution_plan.dict()) if proposal_output else None,
                    proposal_output.quality_score if proposal_output else None,
                    proposal_output.estimated_win_probability if proposal_output else None
                ))
            
            logger.info(f"Proposal saved to history: {history.id}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving proposal to history: {e}")
            return False
    
    def get_recent_proposals(self, limit: int = 10) -> List[ProposalHistory]:
        """Get recent proposals from history"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT id, job_title, client_name, generated_at, status,
                           budget_proposed, final_cost, notes
                    FROM proposals
                    ORDER BY generated_at DESC
                    LIMIT ?
                ''', (limit,))
                
                proposals = []
                for row in cursor.fetchall():
                    proposals.append(ProposalHistory(
                        id=row[0],
                        job_title=row[1],
                        client_name=row[2],
                        generated_at=datetime.fromisoformat(row[3]),
                        status=ProposalStatus(row[4]),
                        budget_proposed=row[5],
                        final_cost=row[6],
                        notes=row[7]
                    ))
                
                return proposals
                
        except Exception as e:
            logger.error(f"Error getting recent proposals: {e}")
            return []
    
    def update_proposal_status(self, proposal_id: str, status: ProposalStatus, 
                             final_cost: Optional[float] = None, 
                             notes: Optional[str] = None) -> bool:
        """Update proposal status"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    UPDATE proposals 
                    SET status = ?, final_cost = ?, notes = ?
                    WHERE id = ?
                ''', (status.value, final_cost, notes, proposal_id))
            
            logger.info(f"Updated proposal {proposal_id} status to {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating proposal status: {e}")
            return False
    
    def get_success_metrics(self, days: int = 30) -> Dict[str, Any]:
        """Get success metrics for the last N days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with sqlite3.connect(self.db_path) as conn:
                # Total proposals
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM proposals
                    WHERE generated_at >= ?
                ''', (cutoff_date.isoformat(),))
                total_proposals = cursor.fetchone()[0]
                
                # Accepted proposals
                cursor = conn.execute('''
                    SELECT COUNT(*) FROM proposals
                    WHERE generated_at >= ? AND status = ?
                ''', (cutoff_date.isoformat(), ProposalStatus.ACCEPTED.value))
                accepted_proposals = cursor.fetchone()[0]
                
                # Average quality score
                cursor = conn.execute('''
                    SELECT AVG(quality_score) FROM proposals
                    WHERE generated_at >= ? AND quality_score IS NOT NULL
                ''', (cutoff_date.isoformat(),))
                avg_quality = cursor.fetchone()[0] or 0.0
                
                # Average budget
                cursor = conn.execute('''
                    SELECT AVG(budget_proposed) FROM proposals
                    WHERE generated_at >= ?
                ''', (cutoff_date.isoformat(),))
                avg_budget = cursor.fetchone()[0] or 0.0
                
                # Total revenue (from accepted proposals)
                cursor = conn.execute('''
                    SELECT SUM(COALESCE(final_cost, budget_proposed)) FROM proposals
                    WHERE generated_at >= ? AND status = ?
                ''', (cutoff_date.isoformat(), ProposalStatus.ACCEPTED.value))
                total_revenue = cursor.fetchone()[0] or 0.0
                
                win_rate = (accepted_proposals / total_proposals * 100) if total_proposals > 0 else 0.0
                
                return {
                    "total_proposals": total_proposals,
                    "accepted_proposals": accepted_proposals,
                    "win_rate": win_rate,
                    "average_quality_score": avg_quality,
                    "average_budget": avg_budget,
                    "total_revenue": total_revenue,
                    "period_days": days
                }
                
        except Exception as e:
            logger.error(f"Error getting success metrics: {e}")
            return {
                "total_proposals": 0,
                "accepted_proposals": 0,
                "win_rate": 0.0,
                "average_quality_score": 0.0,
                "average_budget": 0.0,
                "total_revenue": 0.0,
                "period_days": days
            }