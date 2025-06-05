# Upwork Proposal Generator System
# File: models/core_models.py

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class ProposalStatus(str, Enum):
    """Proposal status enumeration"""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    IGNORED = "ignored"
    PENDING = "pending"

class Priority(str, Enum):
    """Task priority levels"""
    MANDATORY = "mandatory"
    OPTIONAL = "optional"
    NICE_TO_HAVE = "nice_to_have"

class APIProvider(str, Enum):
    """Supported API providers"""
    OPENAI = "openai"
    CLAUDE = "claude"

# Core Data Models
class FreelancerProfile(BaseModel):
    """Freelancer profile configuration"""
    name: str
    hourly_rate: float
    skills: List[str]
    experience_years: int
    specializations: List[str]
    portfolio_examples: List[Dict[str, str]]  # {"title": "", "description": "", "results": ""}
    achievements: List[str]
    languages: List[str] = ["English"]
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

class TaskPlan(BaseModel):
    """Individual task in the execution plan"""
    task: str
    description: str
    role: str  # Data Scientist, ML Engineer, etc.
    hours: float
    rate: float
    priority: Priority
    dependencies: List[str] = Field(default_factory=list)
    
    @property
    def cost(self) -> float:
        return self.hours * self.rate

class ExecutionPlan(BaseModel):
    """Complete execution plan with tasks and costing"""
    tasks: List[TaskPlan]
    total_hours: float
    total_cost: float
    mandatory_cost: float
    optional_cost: float
    notes: List[str] = Field(default_factory=list)
    
    def calculate_totals(self):
        """Recalculate totals based on current tasks"""
        self.total_hours = sum(task.hours for task in self.tasks)
        self.total_cost = sum(task.cost for task in self.tasks)
        self.mandatory_cost = sum(
            task.cost for task in self.tasks 
            if task.priority == Priority.MANDATORY
        )
        self.optional_cost = self.total_cost - self.mandatory_cost

class ProposalTemplate(BaseModel):
    """Proposal template structure"""
    name: str
    sections: Dict[str, str]  # section_name: template_content
    variables: List[str]  # Available variables for substitution
    tone: Literal["professional", "casual", "technical", "creative"]
    
class JobPost(BaseModel):
    """Job posting information"""
    title: str
    description: str
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    duration: Optional[str] = None
    skills_required: List[str] = Field(default_factory=list)
    client_name: Optional[str] = None
    additional_context: Optional[str] = None

class ProposalRequest(BaseModel):
    """Complete proposal generation request"""
    job_post: JobPost
    freelancer_profile: FreelancerProfile
    template_name: str
    api_provider: APIProvider
    max_budget: Optional[float] = None
    error_margin: float = 0.1  # 10% default
    express_mode: bool = False

class ProposalOutput(BaseModel):
    """Generated proposal output"""
    proposal_text: str
    execution_plan: ExecutionPlan
    reviewer_feedback: List[str]
    quality_score: float
    estimated_win_probability: float
    recommendations: List[str]
    
class ProposalHistory(BaseModel):
    """Historical proposal record"""
    id: str
    job_title: str
    client_name: Optional[str]
    generated_at: datetime
    status: ProposalStatus
    budget_proposed: float
    final_cost: Optional[float] = None  # If accepted
    notes: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

# Agent Communication Models
class AgentMessage(BaseModel):
    """Message between agents"""
    from_agent: str
    to_agent: str
    message_type: str
    content: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)

class AgentResponse(BaseModel):
    """Standard agent response format"""
    success: bool
    data: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None
    requires_revision: bool = False
    next_agent: Optional[str] = None

# Configuration Models
class SystemConfig(BaseModel):
    """System-wide configuration"""
    default_api_provider: APIProvider
    default_error_margin: float = 0.1
    max_revision_cycles: int = 3
    output_directory: str = "./proposals"
    profile_directory: str = "./profiles"
    template_directory: str = "./templates"
    
    # API Configuration
    openai_model: str = "gpt-4"
    claude_model: str = "claude-3-sonnet-20240229"
    
    # Quality thresholds
    min_quality_score: float = 0.7
    budget_reduction_warning_threshold: float = 0.3