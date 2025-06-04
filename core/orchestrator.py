# File: core/orchestrator.py

from typing import Dict, Any, Optional, List, Tuple
import logging
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

from langchain.llms import OpenAI
from langchain.chat_models import ChatAnthropic
from models.core_models import (
    ProposalRequest, ProposalOutput, ExecutionPlan, 
    APIProvider, SystemConfig, ProposalTemplate,
    FreelancerProfile, JobPost, AgentResponse
)
from agents.specialized_agents import (
    BusinessTranslatorAgent, CostingAgent, TechnicalValidatorAgent,
    CommercialWriterAgent, ReviewerAgent
)

logger = logging.getLogger(__name__)

class ProcessState(str, Enum):
    """Orchestration process states"""
    INITIALIZING = "initializing"
    TRANSLATING_REQUIREMENTS = "translating_requirements"
    VALIDATING_COSTS = "validating_costs"
    VALIDATING_TECHNICAL = "validating_technical"
    WRITING_PROPOSAL = "writing_proposal"
    REVIEWING_PROPOSAL = "reviewing_proposal"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class ProcessContext:
    """Context object passed between agents"""
    request: ProposalRequest
    template: ProposalTemplate
    current_plan: Optional[ExecutionPlan] = None
    current_proposal: Optional[str] = None
    revision_history: List[Dict[str, Any]] = None
    feedback_chain: List[str] = None
    
    def __post_init__(self):
        if self.revision_history is None:
            self.revision_history = []
        if self.feedback_chain is None:
            self.feedback_chain = []

class ProposalOrchestrator:
    """Central orchestrator for the proposal generation process"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.llm = self._initialize_llm()
        self.agents = self._initialize_agents()
        self.state = ProcessState.INITIALIZING
        self.revision_count = 0
        self.max_revisions = config.max_revision_cycles
        
    def _initialize_llm(self):
        """Initialize the appropriate LLM based on configuration"""
        if self.config.default_api_provider == APIProvider.OPENAI:
            return OpenAI(
                model_name=self.config.openai_model,
                temperature=0.1
            )
        else:
            return ChatAnthropic(
                model=self.config.claude_model,
                temperature=0.1
            )
    
    def _initialize_agents(self) -> Dict[str, Any]:
        """Initialize all specialized agents"""
        return {
            "business_translator": BusinessTranslatorAgent(self.llm),
            "costing_agent": CostingAgent(self.llm),
            "technical_validator": TechnicalValidatorAgent(self.llm),
            "commercial_writer": CommercialWriterAgent(self.llm),
            "reviewer": ReviewerAgent(self.llm)
        }
    
    async def generate_proposal(
        self, 
        request: ProposalRequest,
        template: ProposalTemplate
    ) -> ProposalOutput:
        """Main orchestration method for proposal generation"""
        
        logger.info(f"Starting proposal generation for job: {request.job_post.title}")
        
        context = ProcessContext(
            request=request,
            template=template
        )
        
        try:
            # Execute the main orchestration flow
            result = await self._execute_orchestration_flow(context)
            
            logger.info("Proposal generation completed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Proposal generation failed: {str(e)}")
            self.state = ProcessState.FAILED
            raise
    
    async def _execute_orchestration_flow(self, context: ProcessContext) -> ProposalOutput:
        """Execute the main orchestration flow"""
        
        # Phase 1: Business Translation
        self.state = ProcessState.TRANSLATING_REQUIREMENTS
        execution_plan = await self._translate_requirements(context)
        context.current_plan = execution_plan
        
        # Phase 2: Cost Validation Loop
        self.state = ProcessState.VALIDATING_COSTS
        validated_plan = await self._validate_and_optimize_costs(context)
        context.current_plan = validated_plan
        
        # Phase 3: Technical Validation (Optional)
        if not context.request.express_mode:
            self.state = ProcessState.VALIDATING_TECHNICAL
            await self._validate_technical_feasibility(context)
        
        # Phase 4: Proposal Writing Loop
        self.state = ProcessState.WRITING_PROPOSAL
        proposal_text = await self._write_proposal(context)
        context.current_proposal = proposal_text
        
        # Phase 5: Review and Refinement Loop
        self.state = ProcessState.REVIEWING_PROPOSAL
        final_output = await self._review_and_refine_proposal(context)
        
        self.state = ProcessState.COMPLETED
        return final_output
    
    async def _translate_requirements(self, context: ProcessContext) -> ExecutionPlan:
        """Phase 1: Translate job requirements into execution plan"""
        
        logger.info("Translating job requirements into execution plan")
        
        translator = self.agents["business_translator"]
        
        # Get initial plan
        plan = translator.create_execution_plan(
            job_post=context.request.job_post,
            profile=context.request.freelancer_profile
        )
        
        # Store in revision history
        context.revision_history.append({
            "phase": "business_translation",
            "timestamp": datetime.now().isoformat(),
            "plan": plan.dict(),
            "feedback": None
        })
        
        return plan
    
    async def _validate_and_optimize_costs(self, context: ProcessContext) -> ExecutionPlan:
        """Phase 2: Validate costs and optimize if necessary"""
        
        logger.info("Validating and optimizing costs")
        
        costing_agent = self.agents["costing_agent"]
        current_plan = context.current_plan
        
        # Validate costs
        validation_response = costing_agent.validate_and_optimize_costs(
            plan=current_plan,
            max_budget=context.request.max_budget,
            error_margin=context.request.error_margin
        )
        
        # Check if budget reduction is too significant
        if validation_response.data and not validation_response.success:
            budget_reduction = self._calculate_budget_reduction(
                current_plan, validation_response.data
            )
            
            if budget_reduction > self.config.budget_reduction_warning_threshold:
                logger.warning(f"Budget reduction of {budget_reduction:.1%} exceeds threshold")
                # This would trigger a UI confirmation in the actual implementation
                # For now, we'll continue with the optimization
        
        # If revision is required, iterate with business translator
        if validation_response.requires_revision and self.revision_count < self.max_revisions:
            self.revision_count += 1
            logger.info(f"Cost validation requires revision (attempt {self.revision_count})")
            
            translator = self.agents["business_translator"]
            revised_plan = translator.create_execution_plan(
                job_post=context.request.job_post,
                profile=context.request.freelancer_profile,
                costing_feedback=validation_response.feedback
            )
            
            context.feedback_chain.append(validation_response.feedback)
            context.revision_history.append({
                "phase": "cost_optimization",
                "timestamp": datetime.now().isoformat(),
                "plan": revised_plan.dict(),
                "feedback": validation_response.feedback
            })
            
            # Validate the revised plan
            return await self._validate_and_optimize_costs(context)
        
        return current_plan
    
    async def _validate_technical_feasibility(self, context: ProcessContext) -> None:
        """Phase 3: Validate technical feasibility"""
        
        logger.info("Validating technical feasibility")
        
        validator = self.agents["technical_validator"]
        
        validation_response = validator.validate_technical_feasibility(
            plan=context.current_plan,
            profile=context.request.freelancer_profile,
            job_post=context.request.job_post
        )
        
        # If technical validation fails and requires revision
        if validation_response.requires_revision and self.revision_count < self.max_revisions:
            self.revision_count += 1
            logger.info(f"Technical validation requires revision (attempt {self.revision_count})")
            
            translator = self.agents["business_translator"]
            revised_plan = translator.create_execution_plan(
                job_post=context.request.job_post,
                profile=context.request.freelancer_profile,
                costing_feedback=validation_response.feedback
            )
            
            context.current_plan = revised_plan
            context.feedback_chain.append(validation_response.feedback)
            context.revision_history.append({
                "phase": "technical_validation",
                "timestamp": datetime.now().isoformat(),
                "plan": revised_plan.dict(),
                "feedback": validation_response.feedback
            })
            
            # Re-validate costs for the revised plan
            await self._validate_and_optimize_costs(context)
    
    async def _write_proposal(self, context: ProcessContext) -> str:
        """Phase 4: Write the commercial proposal"""
        
        logger.info("Writing commercial proposal")
        
        writer = self.agents["commercial_writer"]
        
        proposal_text = writer.write_proposal(
            job_post=context.request.job_post,
            plan=context.current_plan,
            profile=context.request.freelancer_profile,
            template=context.template
        )
        
        context.revision_history.append({
            "phase": "proposal_writing",
            "timestamp": datetime.now().isoformat(),
            "proposal": proposal_text,
            "feedback": None
        })
        
        return proposal_text
    
    async def _review_and_refine_proposal(self, context: ProcessContext) -> ProposalOutput:
        """Phase 5: Review and refine the proposal"""
        
        logger.info("Reviewing and refining proposal")
        
        reviewer = self.agents["reviewer"]
        
        review_response = reviewer.review_proposal(
            job_post=context.request.job_post,
            proposal_text=context.current_proposal,
            plan=context.current_plan
        )
        
        # If review requires revision and we haven't exceeded max revisions
        if review_response.requires_revision and self.revision_count < self.max_revisions:
            self.revision_count += 1
            logger.info(f"Proposal review requires revision (attempt {self.revision_count})")
            
            writer = self.agents["commercial_writer"]
            revised_proposal = writer.write_proposal(
                job_post=context.request.job_post,
                plan=context.current_plan,
                profile=context.request.freelancer_profile,
                template=context.template,
                reviewer_feedback=review_response.feedback
            )
            
            context.current_proposal = revised_proposal
            context.feedback_chain.append(review_response.feedback)
            context.revision_history.append({
                "phase": "proposal_revision",
                "timestamp": datetime.now().isoformat(),
                "proposal": revised_proposal,
                "feedback": review_response.feedback
            })
            
            # Re-review the revised proposal
            return await self._review_and_refine_proposal(context)
        
        # Generate final output
        return self._create_final_output(context, review_response)
    
    def _create_final_output(
        self, 
        context: ProcessContext, 
        review_response: AgentResponse
    ) -> ProposalOutput:
        """Create the final proposal output"""
        
        review_data = review_response.data or {}
        
        return ProposalOutput(
            proposal_text=context.current_proposal,
            execution_plan=context.current_plan,
            reviewer_feedback=review_data.get("improvement_suggestions", []),
            quality_score=review_data.get("overall_score", 0.0) / 10.0,
            estimated_win_probability=review_data.get("estimated_win_probability", 0.0) / 100.0,
            recommendations=self._generate_recommendations(context, review_data)
        )
    
    def _generate_recommendations(
        self, 
        context: ProcessContext, 
        review_data: Dict[str, Any]
    ) -> List[str]:
        """Generate actionable recommendations"""
        
        recommendations = []
        
        # Add review-based recommendations
        if "improvement_suggestions" in review_data:
            recommendations.extend(review_data["improvement_suggestions"])
        
        # Add budget-based recommendations
        if context.request.max_budget:
            utilization = context.current_plan.total_cost / context.request.max_budget
            if utilization < 0.7:
                recommendations.append(
                    "Consider adding optional deliverables to maximize budget utilization"
                )
            elif utilization > 0.95:
                recommendations.append(
                    "Budget utilization is very high - consider adding contingency buffer"
                )
        
        # Add revision-based recommendations
        if self.revision_count > 1:
            recommendations.append(
                f"Proposal went through {self.revision_count} revisions - "
                f"consider refining initial requirements gathering"
            )
        
        # Add technical complexity recommendations
        if len(context.current_plan.tasks) > 10:
            recommendations.append(
                "Consider grouping related tasks into phases for better client communication"
            )
        
        return recommendations
    
    def _calculate_budget_reduction(
        self, 
        original_plan: ExecutionPlan, 
        cost_analysis: Dict[str, Any]
    ) -> float:
        """Calculate percentage budget reduction"""
        
        recommended_cuts = cost_analysis.get("cost_breakdown", {}).get("recommended_cuts", 0)
        if recommended_cuts > 0:
            return recommended_cuts / original_plan.total_cost
        return 0.0
    
    def get_process_status(self) -> Dict[str, Any]:
        """Get current process status for UI display"""
        
        return {
            "current_state": self.state.value,
            "revision_count": self.revision_count,
            "max_revisions": self.max_revisions,
            "progress_percentage": self._calculate_progress_percentage()
        }
    
    def _calculate_progress_percentage(self) -> float:
        """Calculate progress percentage based on current state"""
        
        state_progress = {
            ProcessState.INITIALIZING: 0.0,
            ProcessState.TRANSLATING_REQUIREMENTS: 0.2,
            ProcessState.VALIDATING_COSTS: 0.4,
            ProcessState.VALIDATING_TECHNICAL: 0.6,
            ProcessState.WRITING_PROPOSAL: 0.8,
            ProcessState.REVIEWING_PROPOSAL: 0.9,
            ProcessState.COMPLETED: 1.0,
            ProcessState.FAILED: 0.0
        }
        
        return state_progress.get(self.state, 0.0)

class ExpressOrchestrator:
    """Simplified orchestrator for express mode proposals"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.llm = self._initialize_llm()
        
    def _initialize_llm(self):
        """Initialize LLM - same as main orchestrator"""
        if self.config.default_api_provider == APIProvider.OPENAI:
            return OpenAI(
                model_name=self.config.openai_model,
                temperature=0.1
            )
        else:
            return ChatAnthropic(
                model=self.config.claude_model,
                temperature=0.1
            )
    
    async def generate_express_proposal(
        self,
        request: ProposalRequest,
        template: ProposalTemplate
    ) -> ProposalOutput:
        """Generate proposal in express mode - minimal validation"""
        
        logger.info(f"Starting express proposal generation for: {request.job_post.title}")
        
        # Initialize only essential agents
        translator = BusinessTranslatorAgent(self.llm)
        writer = CommercialWriterAgent(self.llm)
        
        try:
            # Step 1: Quick plan generation
            execution_plan = translator.create_execution_plan(
                job_post=request.job_post,
                profile=request.freelancer_profile
            )
            
            # Step 2: Direct proposal writing
            proposal_text = writer.write_proposal(
                job_post=request.job_post,
                plan=execution_plan,
                profile=request.freelancer_profile,
                template=template
            )
            
            # Step 3: Create output with basic quality metrics
            return ProposalOutput(
                proposal_text=proposal_text,
                execution_plan=execution_plan,
                reviewer_feedback="Express mode - no detailed review performed",
                quality_score=0.75,  # Default score for express mode
                estimated_win_probability=0.6,  # Conservative estimate
                recommendations=[
                    "Express mode used - consider full validation for important projects",
                    "Review proposal manually before submission"
                ]
            )
            
        except Exception as e:
            logger.error(f"Express proposal generation failed: {str(e)}")
            raise