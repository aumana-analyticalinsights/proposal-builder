# File: agents/specialized_agents.py

from typing import List, Dict, Any, Optional
from langchain.agents import Agent
from langchain.prompts import PromptTemplate
from langchain.schema import BaseMessage
from crewai import Agent as CrewAgent, Task, Crew
import json
import logging
from models.core_models import (
    FreelancerProfile, JobPost, ExecutionPlan, TaskPlan, 
    Priority, ProposalTemplate, AgentResponse
)

logger = logging.getLogger(__name__)

class BusinessTranslatorAgent:
    """Agent responsible for translating job posts into execution plans"""
    
    def __init__(self, llm):
        self.llm = llm
        self.agent = CrewAgent(
            role="Business Requirements Translator",
            goal="Convert job postings into detailed, actionable execution plans",
            backstory="""You are an experienced project manager and business analyst 
            specialized in data science and AI projects. You excel at breaking down 
            complex requirements into manageable tasks with accurate time estimates.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
    
    def create_execution_plan(
        self, 
        job_post: JobPost, 
        profile: FreelancerProfile,
        costing_feedback: Optional[str] = None
    ) -> ExecutionPlan:
        """Create detailed execution plan from job post"""
        
        task_prompt = f"""
        Based on the job posting and freelancer profile, create a detailed execution plan.
        
        Job Post:
        Title: {job_post.title}
        Description: {job_post.description}
        Budget Range: ${job_post.budget_min} - ${job_post.budget_max}
        Required Skills: {', '.join(job_post.skills_required)}
        
        Freelancer Profile:
        Hourly Rate: ${profile.hourly_rate}
        Skills: {', '.join(profile.skills)}
        Experience: {profile.experience_years} years
        Specializations: {', '.join(profile.specializations)}
        
        {f"Previous Costing Feedback: {costing_feedback}" if costing_feedback else ""}
        
        Create an execution plan with the following structure:
        - Break down the project into specific, measurable tasks
        - Estimate hours for each task realistically
        - Assign appropriate roles (Data Scientist, ML Engineer, etc.)
        - Classify tasks as MANDATORY, OPTIONAL, or NICE_TO_HAVE
        - Consider dependencies between tasks
        
        Return as JSON with this structure:
        {{
            "tasks": [
                {{
                    "task": "Task name",
                    "description": "Detailed description",
                    "role": "Role required",
                    "hours": estimated_hours,
                    "rate": {profile.hourly_rate},
                    "priority": "mandatory|optional|nice_to_have",
                    "dependencies": ["prerequisite_tasks"]
                }}
            ],
            "notes": ["Important considerations"]
        }}
        """
        
        task = Task(
            description=task_prompt,
            agent=self.agent,
            expected_output="JSON formatted execution plan"
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        
        try:
            plan_data = json.loads(result)
            tasks = [TaskPlan(**task_data) for task_data in plan_data["tasks"]]
            
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
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse execution plan JSON: {e}")
            raise ValueError("Failed to generate valid execution plan")

class CostingAgent:
    """Agent responsible for cost validation and optimization"""
    
    def __init__(self, llm):
        self.llm = llm
        self.agent = CrewAgent(
            role="Cost Analysis Specialist",
            goal="Validate project costs and optimize budget allocation",
            backstory="""You are a financial analyst specialized in technology projects. 
            You have deep experience in project costing, resource planning, and budget 
            optimization for data science and AI initiatives.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
    
    def validate_and_optimize_costs(
        self, 
        plan: ExecutionPlan, 
        max_budget: Optional[float],
        error_margin: float = 0.1
    ) -> AgentResponse:
        """Validate costs and suggest optimizations if needed"""
        
        budget_check_prompt = f"""
        Analyze the following execution plan for cost optimization:
        
        Execution Plan:
        Total Cost: ${plan.total_cost:.2f}
        Mandatory Cost: ${plan.mandatory_cost:.2f}
        Optional Cost: ${plan.optional_cost:.2f}
        Total Hours: {plan.total_hours}
        
        Maximum Budget: ${max_budget or 'Not specified'}
        Error Margin: {error_margin * 100}%
        
        Tasks:
        {self._format_tasks_for_analysis(plan.tasks)}
        
        Provide analysis on:
        1. Is the plan within budget constraints?
        2. Are the hour estimates realistic?
        3. Can costs be optimized without compromising quality?
        4. Should any optional tasks be reclassified?
        5. What's the risk level of this estimate?
        
        If budget exceeds limits by more than 30%, suggest specific reductions.
        
        Return as JSON:
        {{
            "within_budget": true/false,
            "budget_utilization": percentage,
            "risk_level": "low|medium|high",
            "optimizations": ["list of specific suggestions"],
            "requires_revision": true/false,
            "feedback_for_translator": "specific feedback if revision needed",
            "cost_breakdown": {{
                "mandatory": dollar_amount,
                "optional": dollar_amount,
                "recommended_cuts": dollar_amount
            }}
        }}
        """
        
        task = Task(
            description=budget_check_prompt,
            agent=self.agent,
            expected_output="JSON formatted cost analysis"
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        
        try:
            analysis = json.loads(result)
            
            return AgentResponse(
                success=analysis["within_budget"],
                data=analysis,
                feedback=analysis.get("feedback_for_translator"),
                requires_revision=analysis["requires_revision"],
                next_agent="business_translator" if analysis["requires_revision"] else "technical_validator"
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse costing analysis: {e}")
            return AgentResponse(
                success=False,
                feedback="Failed to analyze costs properly"
            )
    
    def _format_tasks_for_analysis(self, tasks: List[TaskPlan]) -> str:
        """Format tasks for cost analysis prompt"""
        formatted = []
        for task in tasks:
            formatted.append(
                f"- {task.task} ({task.priority}): {task.hours}h @ ${task.rate} = ${task.cost:.2f}"
            )
        return "\n".join(formatted)

class TechnicalValidatorAgent:
    """Agent for technical feasibility validation"""
    
    def __init__(self, llm):
        self.llm = llm
        self.agent = CrewAgent(
            role="Technical Feasibility Expert",
            goal="Validate technical feasibility of proposed solutions",
            backstory="""You are a senior technical architect with extensive experience 
            in data science, machine learning, and AI systems. You excel at identifying 
            technical risks and ensuring project feasibility.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
    
    def validate_technical_feasibility(
        self, 
        plan: ExecutionPlan, 
        profile: FreelancerProfile,
        job_post: JobPost
    ) -> AgentResponse:
        """Validate if the plan is technically feasible"""
        
        validation_prompt = f"""
        Validate the technical feasibility of this execution plan:
        
        Job Requirements:
        {job_post.description}
        Required Skills: {', '.join(job_post.skills_required)}
        
        Freelancer Capabilities:
        Skills: {', '.join(profile.skills)}
        Experience: {profile.experience_years} years
        Specializations: {', '.join(profile.specializations)}
        
        Proposed Plan:
        {self._format_plan_for_validation(plan)}
        
        Assess:
        1. Does the freelancer have the required skills?
        2. Are the proposed technologies appropriate?
        3. Are there any technical risks or blockers?
        4. Is the timeline realistic for the technical complexity?
        5. Are there missing technical considerations?
        
        Return as JSON:
        {{
            "feasible": true/false,
            "confidence_level": "high|medium|low",
            "technical_risks": ["list of risks"],
            "missing_skills": ["skills not covered"],
            "recommendations": ["technical recommendations"],
            "requires_revision": true/false,
            "feedback_for_translator": "feedback if revision needed"
        }}
        """
        
        task = Task(
            description=validation_prompt,
            agent=self.agent,
            expected_output="JSON formatted technical validation"
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        
        try:
            validation = json.loads(result)
            
            return AgentResponse(
                success=validation["feasible"],
                data=validation,
                feedback=validation.get("feedback_for_translator"),
                requires_revision=validation["requires_revision"],
                next_agent="business_translator" if validation["requires_revision"] else "commercial_writer"
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse technical validation: {e}")
            return AgentResponse(
                success=False,
                feedback="Failed to validate technical feasibility"
            )
    
    def _format_plan_for_validation(self, plan: ExecutionPlan) -> str:
        """Format plan for technical validation"""
        formatted = []
        for task in plan.tasks:
            formatted.append(
                f"- {task.task}: {task.description} ({task.hours}h, {task.role})"
            )
        return "\n".join(formatted)

class CommercialWriterAgent:
    """Agent responsible for writing compelling proposals"""
    
    def __init__(self, llm):
        self.llm = llm
        self.agent = CrewAgent(
            role="Proposal Writing Specialist",
            goal="Create compelling, professional proposals that win projects",
            backstory="""You are an expert proposal writer with a proven track record 
            of winning high-value freelance projects. You understand client psychology 
            and know how to position technical capabilities in business terms.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
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
        
        proposal_prompt = f"""
        Write a compelling proposal for this Upwork job:
        
        Job Details:
        Title: {job_post.title}
        Description: {job_post.description}
        Budget: ${job_post.budget_min} - ${job_post.budget_max}
        Client: {job_post.client_name or 'Not specified'}
        
        Execution Plan:
        Total Cost: ${plan.total_cost:.2f}
        Timeline: {plan.total_hours} hours
        Key Tasks:
        {self._format_key_tasks(plan.tasks[:5])}  # Top 5 tasks
        
        Freelancer Profile:
        {profile.name} - {profile.experience_years} years experience
        Specializations: {', '.join(profile.specializations)}
        Key Achievements: {'; '.join(profile.achievements[:3])}
        
        Template Style: {template.tone}
        
        {f"Reviewer Feedback to Address: {reviewer_feedback}" if reviewer_feedback else ""}
        
        Write a proposal that:
        1. Demonstrates clear understanding of the project
        2. Highlights relevant experience and achievements
        3. Presents a structured approach with clear deliverables
        4. Addresses potential client concerns
        5. Includes a compelling call to action
        6. Maintains a {template.tone} tone throughout
        
        Structure the proposal with clear sections and make it scannable.
        Include pricing information naturally without making it the focus.
        """
        
        task = Task(
            description=proposal_prompt,
            agent=self.agent,
            expected_output="Complete proposal text ready for submission"
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        return result
    
    def _format_key_tasks(self, tasks: List[TaskPlan]) -> str:
        """Format key tasks for proposal writing"""
        formatted = []
        for i, task in enumerate(tasks, 1):
            formatted.append(f"{i}. {task.task}: {task.description}")
        return "\n".join(formatted)

class ReviewerAgent:
    """Agent responsible for proposal quality review"""
    
    def __init__(self, llm):
        self.llm = llm
        self.agent = CrewAgent(
            role="Client Perspective Reviewer",
            goal="Evaluate proposals from the client's perspective",
            backstory="""You are an experienced project manager who frequently hires 
            freelancers on Upwork. You know what makes a proposal stand out and what 
            red flags to avoid. You evaluate proposals with a critical, client-focused eye.""",
            verbose=True,
            allow_delegation=False,
            llm=llm
        )
    
    def review_proposal(
        self,
        job_post: JobPost,
        proposal_text: str,
        plan: ExecutionPlan
    ) -> AgentResponse:
        """Review proposal from client perspective"""
        
        review_prompt = f"""
        As a client who posted this job, review the following proposal:
        
        Original Job Post:
        {job_post.title}
        {job_post.description}
        Budget: ${job_post.budget_min} - ${job_post.budget_max}
        
        Freelancer's Proposal:
        {proposal_text}
        
        Proposed Budget: ${plan.total_cost:.2f}
        Timeline: {plan.total_hours} hours
        
        Evaluate this proposal on:
        1. Does the freelancer understand my requirements?
        2. Do they have relevant experience for this project?
        3. Is the approach realistic and well-structured?
        4. Is the pricing reasonable and justified?
        5. Does the proposal inspire confidence?
        6. Are there any red flags or concerns?
        7. Would I shortlist this freelancer?
        
        Return as JSON:
        {{
            "overall_score": score_out_of_10,
            "would_shortlist": true/false,
            "strengths": ["list of strengths"],
            "weaknesses": ["list of weaknesses"],
            "red_flags": ["list of concerns"],
            "improvement_suggestions": ["specific suggestions"],
            "estimated_win_probability": percentage,
            "requires_revision": true/false,
            "feedback_for_writer": "specific feedback if revision needed"
        }}
        """
        
        task = Task(
            description=review_prompt,
            agent=self.agent,
            expected_output="JSON formatted proposal review"
        )
        
        crew = Crew(
            agents=[self.agent],
            tasks=[task],
            verbose=True
        )
        
        result = crew.kickoff()
        
        try:
            review = json.loads(result)
            
            return AgentResponse(
                success=review["overall_score"] >= 7.0,  # Minimum acceptable score
                data=review,
                feedback=review.get("feedback_for_writer"),
                requires_revision=review["requires_revision"],
                next_agent="commercial_writer" if review["requires_revision"] else None
            )
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse proposal review: {e}")
            return AgentResponse(
                success=False,
                feedback="Failed to review proposal properly"
            )