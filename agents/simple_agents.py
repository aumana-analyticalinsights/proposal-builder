# File: agents/simple_agents.py
# Python 3.13 compatible agents without CrewAI

from typing import List, Dict, Any, Optional
import json
import logging
from abc import ABC, abstractmethod

from models.core_models import (
    FreelancerProfile, JobPost, ExecutionPlan, TaskPlan, 
    Priority, ProposalTemplate, AgentResponse
)

logger = logging.getLogger(__name__)

class BaseLLMAgent(ABC):
    """Base class for all LLM-powered agents"""
    
    def __init__(self, llm, role: str, goal: str):
        self.llm = llm
        self.role = role
        self.goal = goal
    
    def _call_llm(self, prompt: str) -> str:
        """Call the LLM with the given prompt"""
        try:
            # Handle different LLM interfaces
            if hasattr(self.llm, 'invoke'):
                # LangChain ChatModel interface
                response = self.llm.invoke(prompt)
                return response.content if hasattr(response, 'content') else str(response)
            elif hasattr(self.llm, 'generate'):
                # LangChain LLM interface
                response = self.llm.generate([prompt])
                return response.generations[0][0].text
            elif hasattr(self.llm, 'complete'):
                # Direct completion interface
                return self.llm.complete(prompt)
            else:
                # Fallback for other interfaces
                return str(self.llm(prompt))
        except Exception as e:
            logger.error(f"LLM call failed for {self.role}: {e}")
            return f"Error: Unable to generate response for {self.role}"

class BusinessTranslatorAgent(BaseLLMAgent):
    """Agent responsible for translating job posts into execution plans"""
    
    def __init__(self, llm):
        super().__init__(
            llm=llm,
            role="Business Requirements Translator",
            goal="Convert job postings into detailed, actionable execution plans"
        )
    
    def create_execution_plan(
        self, 
        job_post: JobPost, 
        profile: FreelancerProfile,
        costing_feedback: Optional[str] = None
    ) -> ExecutionPlan:
        """Create detailed execution plan from job post"""
        
        prompt = self._build_translation_prompt(job_post, profile, costing_feedback)
        response = self._call_llm(prompt)
        
        try:
            plan_data = self._parse_json_response(response)
            return self._build_execution_plan(plan_data, profile.hourly_rate)
        except Exception as e:
            logger.error(f"Failed to create execution plan: {e}")
            return self._create_fallback_plan(job_post, profile)
    
    def _build_translation_prompt(self, job_post: JobPost, profile: FreelancerProfile, 
                                 costing_feedback: Optional[str]) -> str:
        """Build the prompt for business translation"""
        
        feedback_section = f"\n\nPrevious Costing Feedback: {costing_feedback}\nPlease adjust the plan accordingly." if costing_feedback else ""
        
        return f"""
        You are an experienced project manager and business analyst specialized in data science and AI projects.
        
        Create a detailed execution plan for this project:
        
        JOB POSTING:
        Title: {job_post.title}
        Description: {job_post.description}
        Budget Range: ${job_post.budget_min} - ${job_post.budget_max}
        Required Skills: {', '.join(job_post.skills_required)}
        
        FREELANCER PROFILE:
        Hourly Rate: ${profile.hourly_rate}
        Skills: {', '.join(profile.skills)}
        Experience: {profile.experience_years} years
        Specializations: {', '.join(profile.specializations)}
        {feedback_section}
        
        INSTRUCTIONS:
        Break down the project into specific, measurable tasks with realistic hour estimates.
        Classify each task priority as: "mandatory", "optional", or "nice_to_have"
        Assign appropriate roles: Data Scientist, ML Engineer, Data Analyst, etc.
        
        RESPOND WITH VALID JSON ONLY:
        {{
            "tasks": [
                {{
                    "task": "Clear task name",
                    "description": "Detailed description of what will be done",
                    "role": "Data Scientist",
                    "hours": 10.0,
                    "rate": {profile.hourly_rate},
                    "priority": "mandatory",
                    "dependencies": []
                }}
            ],
            "notes": ["Important considerations or assumptions"]
        }}
        """
    
    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        # Find JSON in response
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        
        if start_idx == -1 or end_idx == 0:
            raise ValueError("No JSON found in response")
        
        json_str = response[start_idx:end_idx]
        return json.loads(json_str)
    
    def _build_execution_plan(self, plan_data: Dict[str, Any], hourly_rate: float) -> ExecutionPlan:
        """Build ExecutionPlan from parsed data"""
        tasks = []
        
        for task_data in plan_data["tasks"]:
            # Validate and normalize priority
            priority_str = task_data.get("priority", "mandatory").lower().replace("-", "_")
            if priority_str not in ["mandatory", "optional", "nice_to_have"]:
                priority_str = "mandatory"
            
            task = TaskPlan(
                task=task_data["task"],
                description=task_data["description"],
                role=task_data["role"],
                hours=float(task_data["hours"]),
                rate=float(task_data.get("rate", hourly_rate)),
                priority=Priority(priority_str),
                dependencies=task_data.get("dependencies", [])
            )
            tasks.append(task)
        
        execution_plan = ExecutionPlan(
            tasks=tasks,
            total_hours=0,
            total_cost=0,
            mandatory_cost=0,
            optional_cost=0,
            notes=plan_data.get("notes", [])
        )
        execution_plan.calculate_totals()
        return execution_plan
    
    def _create_fallback_plan(self, job_post: JobPost, profile: FreelancerProfile) -> ExecutionPlan:
        """Create a basic fallback plan if parsing fails"""
        tasks = [
            TaskPlan(
                task="Project Analysis and Requirements Gathering",
                description="Analyze project requirements and define scope",
                role="Data Scientist",
                hours=8.0,
                rate=profile.hourly_rate,
                priority=Priority.MANDATORY
            ),
            TaskPlan(
                task="Data Collection and Preprocessing",
                description="Gather, clean, and prepare data for analysis",
                role="Data Scientist",
                hours=20.0,
                rate=profile.hourly_rate,
                priority=Priority.MANDATORY
            ),
            TaskPlan(
                task="Model Development and Training",
                description="Develop and train machine learning models",
                role="ML Engineer",
                hours=30.0,
                rate=profile.hourly_rate,
                priority=Priority.MANDATORY
            ),
            TaskPlan(
                task="Results Analysis and Reporting",
                description="Analyze results and create comprehensive report",
                role="Data Scientist",
                hours=12.0,
                rate=profile.hourly_rate,
                priority=Priority.MANDATORY
            ),
            TaskPlan(
                task="Model Deployment and Documentation",
                description="Deploy model and create technical documentation",
                role="ML Engineer",
                hours=10.0,
                rate=profile.hourly_rate,
                priority=Priority.OPTIONAL
            )
        ]
        
        plan = ExecutionPlan(
            tasks=tasks,
            total_hours=0,
            total_cost=0,
            mandatory_cost=0,
            optional_cost=0,
            notes=["Auto-generated fallback plan"]
        )
        plan.calculate_totals()
        return plan

class CostingAgent(BaseLLMAgent):
    """Agent responsible for cost validation and optimization"""
    
    def __init__(self, llm):
        super().__init__(
            llm=llm,
            role="Cost Analysis Specialist",
            goal="Validate project costs and optimize budget allocation"
        )
    
    def validate_and_optimize_costs(
        self, 
        plan: ExecutionPlan, 
        max_budget: Optional[float],
        error_margin: float = 0.1
    ) -> AgentResponse:
        """Validate costs and suggest optimizations if needed"""
        
        # Basic budget validation
        within_budget = True
        feedback = None
        requires_revision = False
        
        if max_budget:
            budget_with_margin = max_budget * (1 + error_margin)
            within_budget = plan.total_cost <= budget_with_margin
            
            if not within_budget:
                excess_percentage = (plan.total_cost - max_budget) / max_budget
                if excess_percentage > 0.3:  # More than 30% over budget
                    requires_revision = True
                    feedback = (
                        f"Project cost ${plan.total_cost:.0f} exceeds budget by {excess_percentage:.1%}. "
                        f"Consider reducing scope of optional tasks or optimizing task estimates."
                    )
        
        # Get LLM analysis for more detailed feedback
        if max_budget and plan.total_cost > max_budget * 0.8:  # If close to or over budget
            llm_feedback = self._get_llm_cost_analysis(plan, max_budget, error_margin)
            if llm_feedback and not feedback:
                feedback = llm_feedback
        
        return AgentResponse(
            success=within_budget,
            data={
                "within_budget": within_budget,
                "budget_utilization": (plan.total_cost / max_budget * 100) if max_budget else 0,
                "risk_level": "high" if not within_budget else ("medium" if plan.total_cost > max_budget * 0.9 else "low"),
                "requires_revision": requires_revision,
                "total_cost": plan.total_cost,
                "mandatory_cost": plan.mandatory_cost,
                "optional_cost": plan.optional_cost
            },
            feedback=feedback,
            requires_revision=requires_revision,
            next_agent="business_translator" if requires_revision else "commercial_writer"
        )
    
    def _get_llm_cost_analysis(self, plan: ExecutionPlan, max_budget: float, error_margin: float) -> Optional[str]:
        """Get detailed cost analysis from LLM"""
        try:
            prompt = f"""
            Analyze this project cost breakdown:
            
            Maximum Budget: ${max_budget:.0f}
            Current Total: ${plan.total_cost:.0f}
            Mandatory Tasks: ${plan.mandatory_cost:.0f}
            Optional Tasks: ${plan.optional_cost:.0f}
            
            Tasks:
            {self._format_tasks_for_analysis(plan.tasks)}
            
            Provide brief recommendations for cost optimization if the total exceeds 90% of budget.
            Focus on practical suggestions. Keep response under 100 words.
            """
            
            response = self._call_llm(prompt)
            return response if "Error:" not in response else None
        except Exception:
            return None
    
    def _format_tasks_for_analysis(self, tasks: List[TaskPlan]) -> str:
        """Format tasks for cost analysis"""
        formatted = []
        for task in tasks:
            formatted.append(f"- {task.task} ({task.priority.value}): {task.hours}h @ ${task.rate} = ${task.cost:.0f}")
        return "\n".join(formatted)

class CommercialWriterAgent(BaseLLMAgent):
    """Agent responsible for writing compelling proposals"""
    
    def __init__(self, llm):
        super().__init__(
            llm=llm,
            role="Proposal Writing Specialist",
            goal="Create compelling, professional proposals that win projects"
        )
    
    def write_proposal(
        self,
        job_post: JobPost,
        plan: ExecutionPlan,
        profile: FreelancerProfile,
        template: ProposalTemplate,
        reviewer_feedback: Optional[str] = None
    ) -> str:
        """Write a compelling proposal"""
        
        prompt = self._build_writing_prompt(job_post, plan, profile, template, reviewer_feedback)
        return self._call_llm(prompt)
    
    def _build_writing_prompt(self, job_post: JobPost, plan: ExecutionPlan, 
                             profile: FreelancerProfile, template: ProposalTemplate,
                             reviewer_feedback: Optional[str]) -> str:
        """Build the prompt for proposal writing"""
        
        key_tasks = [f"• {task.task}: {task.description}" for task in plan.tasks[:5]]
        feedback_section = f"\n\nREVIEWER FEEDBACK TO ADDRESS:\n{reviewer_feedback}" if reviewer_feedback else ""
        
        return f"""
        You are an expert proposal writer with a proven track record of winning high-value Upwork projects.
        
        Write a compelling proposal for this job:
        
        JOB DETAILS:
        Title: {job_post.title}
        Description: {job_post.description}
        Budget: ${job_post.budget_min} - ${job_post.budget_max}
        Client: {job_post.client_name or 'there'}
        
        MY PROFILE:
        Name: {profile.name}
        Experience: {profile.experience_years} years
        Specializations: {', '.join(profile.specializations)}
        Key Skills: {', '.join(profile.skills[:8])}
        Top Achievements: {'; '.join(profile.achievements[:3])}
        
        PROJECT PLAN:
        Total Investment: ${plan.total_cost:.0f}
        Timeline: {plan.total_hours:.0f} hours
        Key Deliverables:
        {chr(10).join(key_tasks)}
        
        TEMPLATE TONE: {template.tone}
        {feedback_section}
        
        Write a {template.tone} proposal (400-600 words) that:
        1. Shows deep understanding of their needs
        2. Highlights my most relevant experience
        3. Presents clear methodology and deliverables
        4. Builds confidence in my expertise
        5. Includes compelling call to action
        
        Make it scannable with clear sections and persuasive but not salesy.
        """

class ReviewerAgent(BaseLLMAgent):
    """Agent responsible for proposal quality review"""
    
    def __init__(self, llm):
        super().__init__(
            llm=llm,
            role="Client Perspective Reviewer",
            goal="Evaluate proposals from the client's perspective"
        )
    
    def review_proposal(
        self,
        job_post: JobPost,
        proposal_text: str,
        plan: ExecutionPlan
    ) -> AgentResponse:
        """Review proposal from client perspective"""
        
        prompt = f"""
        You are a client who posted this job on Upwork. Review this freelancer's proposal:
        
        YOUR JOB POST:
        {job_post.title}
        {job_post.description[:400]}...
        Budget: ${job_post.budget_min} - ${job_post.budget_max}
        
        FREELANCER'S PROPOSAL:
        {proposal_text}
        
        THEIR PRICING: ${plan.total_cost:.0f} for {plan.total_hours:.0f} hours
        
        Rate this proposal from 1-10 considering:
        - Understanding of requirements
        - Relevant experience demonstration  
        - Clear methodology and deliverables
        - Professional communication
        - Value for money
        - Likelihood to hire this freelancer
        
        Respond with this exact format:
        SCORE: X/10
        STRENGTHS: [list 2-3 key strengths]
        WEAKNESSES: [list 1-2 areas for improvement]
        WOULD_HIRE: Yes/No
        FEEDBACK: [specific suggestions if score < 8]
        """
        
        response = self._call_llm(prompt)
        return self._parse_review_response(response)
    
    def _parse_review_response(self, response: str) -> AgentResponse:
        """Parse the review response"""
        try:
            lines = response.strip().split('\n')
            score_line = next((line for line in lines if 'SCORE:' in line.upper()), '')
            strengths_line = next((line for line in lines if 'STRENGTHS:' in line.upper()), '')
            weaknesses_line = next((line for line in lines if 'WEAKNESSES:' in line.upper()), '')
            would_hire_line = next((line for line in lines if 'WOULD_HIRE:' in line.upper()), '')
            feedback_line = next((line for line in lines if 'FEEDBACK:' in line.upper()), '')
            
            # Extract score
            score = 7.0  # Default
            if score_line:
                score_text = score_line.split(':')[1].strip()
                score = float(score_text.split('/')[0])
            
            # Extract would hire
            would_hire = 'yes' in would_hire_line.lower() if would_hire_line else score >= 7
            
            # Determine if revision needed
            requires_revision = score < 7.0 or not would_hire
            
            return AgentResponse(
                success=score >= 7.0,
                data={
                    "overall_score": score,
                    "would_shortlist": would_hire,
                    "strengths": [strengths_line.split(':', 1)[1].strip()] if strengths_line else [],
                    "weaknesses": [weaknesses_line.split(':', 1)[1].strip()] if weaknesses_line else [],
                    "estimated_win_probability": min(score * 10, 90),  # Convert to percentage
                    "requires_revision": requires_revision
                },
                feedback=feedback_line.split(':', 1)[1].strip() if feedback_line else None,
                requires_revision=requires_revision,
                next_agent="commercial_writer" if requires_revision else None
            )
            
        except Exception as e:
            logger.error(f"Failed to parse review response: {e}")
            return AgentResponse(
                success=True,  # Default to success to avoid infinite loops
                data={
                    "overall_score": 7.5,
                    "would_shortlist": True,
                    "strengths": ["Proposal generated successfully"],
                    "weaknesses": ["Review parsing failed"],
                    "estimated_win_probability": 75,
                    "requires_revision": False
                },
                feedback="Review completed with default scoring",
                requires_revision=False
            )