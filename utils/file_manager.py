# File: utils/file_manager.py
import json
import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime

from models.core_models import FreelancerProfile, ProposalTemplate, ProposalHistory

logger = logging.getLogger(__name__)

class FileManager:
    """Handles all file operations for the application"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.profiles_dir = self.base_dir / "profiles"
        self.templates_dir = self.base_dir / "templates"
        self.outputs_dir = self.base_dir / "outputs"
        self.history_dir = self.base_dir / "history"
        
        # Create directories if they don't exist
        self._ensure_directories()
    
    def _ensure_directories(self):
        """Create necessary directories"""
        for directory in [self.profiles_dir, self.templates_dir, 
                         self.outputs_dir, self.history_dir]:
            directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Ensured directory exists: {directory}")
    
    # Profile Management
    def list_profiles(self) -> List[str]:
        """List all available freelancer profiles"""
        try:
            profiles = []
            for file_path in self.profiles_dir.glob("*.json"):
                profiles.append(file_path.name)
            return sorted(profiles)
        except Exception as e:
            logger.error(f"Error listing profiles: {e}")
            return []
    
    def load_profile(self, filename: str) -> Optional[FreelancerProfile]:
        """Load a freelancer profile from file"""
        try:
            file_path = self.profiles_dir / filename
            if not file_path.exists():
                logger.error(f"Profile file not found: {filename}")
                return None
            
            with open(file_path, 'r', encoding='utf-8') as f:
                profile_data = json.load(f)
            
            return FreelancerProfile(**profile_data)
            
        except Exception as e:
            logger.error(f"Error loading profile {filename}: {e}")
            return None
    
    def save_profile(self, profile: FreelancerProfile, filename: str) -> bool:
        """Save a freelancer profile to file"""
        try:
            file_path = self.profiles_dir / filename
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(profile.dict(), f, indent=2, ensure_ascii=False)
            
            logger.info(f"Profile saved: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving profile {filename}: {e}")
            return False
    
    # Template Management
    def list_templates(self) -> List[str]:
        """List all available proposal templates"""
        try:
            templates = []
            for file_path in self.templates_dir.glob("*.json"):
                templates.append(file_path.stem)  # Remove .json extension
            return sorted(templates)
        except Exception as e:
            logger.error(f"Error listing templates: {e}")
            return ["default"]  # Return default if error
    
    def load_template(self, template_name: str) -> Optional[ProposalTemplate]:
        """Load a proposal template"""
        try:
            file_path = self.templates_dir / f"{template_name}.json"
            
            if not file_path.exists():
                # Return default template if file doesn't exist
                return self._get_default_template()
            
            with open(file_path, 'r', encoding='utf-8') as f:
                template_data = json.load(f)
            
            return ProposalTemplate(**template_data)
            
        except Exception as e:
            logger.error(f"Error loading template {template_name}: {e}")
            return self._get_default_template()
    
    def save_template(self, template: ProposalTemplate) -> bool:
        """Save a proposal template"""
        try:
            file_path = self.templates_dir / f"{template.name}.json"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template.dict(), f, indent=2, ensure_ascii=False)
            
            logger.info(f"Template saved: {template.name}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving template {template.name}: {e}")
            return False
    
    def _get_default_template(self) -> ProposalTemplate:
        """Get default proposal template"""
        return ProposalTemplate(
            name="default",
            sections={
                "greeting": "Hello {client_name},\\n\\nI hope this message finds you well.",
                "understanding": "I've carefully reviewed your project requirements for {job_title} and I'm confident I can deliver exceptional results.",
                "approach": "Here's my proposed approach:\\n{execution_plan}",
                "experience": "With {experience_years} years of experience in {specializations}, I bring proven expertise to your project.",
                "pricing": "Based on the scope, I estimate {total_hours} hours at ${hourly_rate}/hour, totaling ${total_cost}.",
                "closing": "I'm excited about the opportunity to work with you and would love to discuss this project further.\\n\\nBest regards,\\n{freelancer_name}"
            },
            variables=["client_name", "job_title", "execution_plan", "experience_years", 
                      "specializations", "total_hours", "hourly_rate", "total_cost", "freelancer_name"],
            tone="professional"
        )
    
    # Output Management
    def save_proposal_output(self, proposal_text: str, execution_plan, 
                           job_title: str, timestamp: Optional[datetime] = None) -> str:
        """Save proposal output to files"""
        if timestamp is None:
            timestamp = datetime.now()
        
        # Create unique directory for this proposal
        safe_title = "".join(c for c in job_title if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_title = safe_title.replace(' ', '_')[:50]  # Limit length
        
        proposal_dir = self.outputs_dir / f"{timestamp.strftime('%Y%m%d_%H%M%S')}_{safe_title}"
        proposal_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            # Save proposal text
            proposal_file = proposal_dir / "proposal.txt"
            with open(proposal_file, 'w', encoding='utf-8') as f:
                f.write(proposal_text)
            
            # Save execution plan as CSV
            import pandas as pd
            tasks_data = []
            for task in execution_plan.tasks:
                tasks_data.append({
                    "Task": task.task,
                    "Description": task.description,
                    "Role": task.role,
                    "Hours": task.hours,
                    "Rate": task.rate,
                    "Priority": task.priority.value
                })
            
            df = pd.DataFrame(tasks_data)
            csv_file = proposal_dir / "execution_plan.csv"
            df.to_csv(csv_file, index=False)
            
            # Save metadata
            metadata = {
                "job_title": job_title,
                "generated_at": timestamp.isoformat(),
                "total_cost": execution_plan.total_cost,
                "total_hours": execution_plan.total_hours,
                "mandatory_cost": execution_plan.mandatory_cost,
                "optional_cost": execution_plan.optional_cost
            }
            
            metadata_file = proposal_dir / "metadata.json"
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2)
            
            logger.info(f"Proposal saved to: {proposal_dir}")
            return str(proposal_dir)
            
        except Exception as e:
            logger.error(f"Error saving proposal output: {e}")
            return ""