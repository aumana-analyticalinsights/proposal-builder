# File: core/simple_orchestrator.py
# Simplified orchestrator compatible with Python 3.13

import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

# LangChain imports for LLM initialization
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from models.core_models import (
    ProposalRequest, ProposalOutput, ExecutionPlan, 
    APIProvider, SystemConfig, ProposalTemplate,
    FreelancerProfile, JobPost
)
from agents.simple_agents import (
    BusinessTranslatorAgent, CostingAgent, 
    CommercialWriterAgent, ReviewerAgent
)

logger = logging.getLogger(__name__)

class ProcessState(str, Enum):
    """Orchestration process states"""
    INITIALIZING = "initializing"
    TRANSLATING_REQUIREMENTS = "translating_requirements"
    VALIDATING_COSTS = "validating_costs"
    WRITING_PROPOSAL = "writing_proposal"
    REVIEWING_PROPOSAL = "reviewing_proposal"
    COMPLETED = "completed"
    FAILED = "failed"

class SimpleProposalOrchestrator:
    """Simplified central orchestrator for proposal generation"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.llm = self._initialize_llm()
        self.agents = self._initialize_agents()
        self.state = ProcessState.INITIALIZING
        self.revision_count = 0
        self.max_revisions = config.max_revision_cycles
        
    def _initialize_llm(self):
        """Initialize the appropriate LLM based on configuration"""
        try:
            if self.config.default_api_provider == APIProvider.OPENAI:
                api_key = os.getenv('OPENAI_API_KEY')
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment variables")
                
                return ChatOpenAI(
                    model=self.config.openai_model,
                    temperature=0.1,
                    api_key=api_key
                )
            else:
                api_key = os.getenv('ANTHROPIC_API_KEY')
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
                
                return ChatAnthropic(
                    model=self.config.claude_model,
                    temperature=0.1,
                    api_key=api_key
                )
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            # Return a mock LLM for testing
            return self._create_mock_llm()
    
    def _create_mock_llm(self):
        """Create a mock LLM for testing when API keys are not available"""
        class MockLLM:
            def invoke(self, prompt):
                class MockResponse:
                    content = "Mock response for testing purposes"
                return MockResponse()
        
        logger.warning("Using mock LLM - set proper API keys for full functionality")
        return MockLLM()
    
    def _initialize_agents(self) -> Dict[str, Any]:
        """Initialize all specialized agents"""
        return {
            "business_translator": BusinessTranslatorAgent(self.llm),
            "costing_agent": CostingAgent(self.llm),
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
        
        try:
            # Phase 1: Business Translation
            self.state = ProcessState.TRANSLATING_REQUIREMENTS
            execution_plan = self._translate_requirements(request)
            
            # Phase 2: Cost Validation
            self.state = ProcessState.VALIDATING_COSTS
            validated_plan = self._validate_costs(execution_plan, request)
            
            # Phase 3: Proposal Writing
            self.state = ProcessState.WRITING_PROPOSAL
            proposal_text = self._write_proposal(request, validated_plan, template)
            
            # Phase 4: Review and Quality Check
            self.state = ProcessState.REVIEWING_PROPOSAL
            final_output = self._review_proposal(request, proposal_text, validated_plan)
            
            self.state = ProcessState.COMPLETED
            logger.info("Proposal generation completed successfully")
            return final_output
            
        except Exception as e:
            logger.error(f"Proposal generation failed: {str(e)}")
            self.state = ProcessState.FAILED
            raise
    
    def _translate_requirements(self, request: ProposalRequest) -> ExecutionPlan:
        """Phase 1: Translate job requirements into execution plan"""
        logger.info("Translating job requirements into execution plan")
        
        translator = self.agents["business_translator"]
        plan = translator.create_execution_plan(
            job_post=request.job_post,
            profile=request.freelancer_profile
        )
        
        return plan
    
    def _validate_costs(self, plan: ExecutionPlan, request: ProposalRequest) -> ExecutionPlan:
        """Phase 2: Validate costs and optimize if necessary"""
        logger.info("Validating and optimizing costs")
        
        costing_agent = self.agents["costing_agent"]
        validation_response = costing_agent.validate_and_optimize_costs(
            plan=plan,
            max_budget=request.max_budget,
            error_margin=request.error_margin
        )
        
        # If revision is required and we haven't exceeded max revisions
        if validation_response.requires_revision and self.revision_count < self.max_revisions:
            self.revision_count += 1
            logger.info(f"Cost validation requires revision (attempt {self.revision_count})")
            
            # Get revised plan from translator
            translator = self.agents["business_translator"]
            revised_plan = translator.create_execution_plan(
                job_post=request.job_post,
                profile=request.freelancer_profile,
                costing_feedback=validation_response.feedback
            )
            
            # Recursively validate the revised plan
            return self._validate_costs(revised_plan, request)
        
        return plan
    
    def _write_proposal(
        self, 
        request: ProposalRequest, 
        plan: ExecutionPlan, 
        template: ProposalTemplate
    ) -> str:
        """Phase 3: Write the commercial proposal"""
        logger.info("Writing commercial proposal")
        
        writer = self.agents["commercial_writer"]
        proposal_text = writer.write_proposal(
            job_post=request.job_post,
            plan=plan,
            profile=request.freelancer_profile,
            template=template
        )
        
        return proposal_text
    
    def _review_proposal(
        self, 
        request: ProposalRequest, 
        proposal_text: str, 
        plan: ExecutionPlan
    ) -> ProposalOutput:
        """Phase 4: Review and finalize the proposal"""
        logger.info("Reviewing and finalizing proposal")
        
        reviewer = self.agents["reviewer"]
        review_response = reviewer.review_proposal(
            job_post=request.job_post,
            proposal_text=proposal_text,
            plan=plan
        )
        
        # If review requires revision and we haven't exceeded max revisions
        if review_response.requires_revision and self.revision_count < self.max_revisions:
            self.revision_count += 1
            logger.info(f"Proposal review requires revision (attempt {self.revision_count})")
            
            # Get revised proposal from writer
            writer = self.agents["commercial_writer"]
            revised_proposal = writer.write_proposal(
                job_post=request.job_post,
                plan=plan,
                profile=request.freelancer_profile,
                template=request.template_name,  # Use template name here
                reviewer_feedback=review_response.feedback
            )
            
            # Recursively review the revised proposal
            return self._review_proposal(request, revised_proposal, plan)
        
        # Generate final output
        return self._create_final_output(proposal_text, plan, review_response)
    
    def _create_final_output(
        self, 
        proposal_text: str, 
        plan: ExecutionPlan,
        review_response
    ) -> ProposalOutput:
        """Create the final proposal output"""
        
        review_data = review_response.data or {}
        
        return ProposalOutput(
            proposal_text=proposal_text,
            execution_plan=plan,
            reviewer_feedback=review_data.get("strengths", []) + review_data.get("weaknesses", []),
            quality_score=review_data.get("overall_score", 7.5) / 10.0,
            estimated_win_probability=review_data.get("estimated_win_probability", 75.0) / 100.0,
            recommendations=self._generate_recommendations(review_data)
        )
    
    def _generate_recommendations(self, review_data: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []
        
        # Add review-based recommendations
        if "weaknesses" in review_data and review_data["weaknesses"]:
            for weakness in review_data["weaknesses"]:
                if weakness.strip():
                    recommendations.append(f"Improve: {weakness}")
        
        # Add score-based recommendations
        score = review_data.get("overall_score", 7.5)
        if score < 8.0:
            recommendations.append("Consider enhancing the value proposition and client benefits")
        
        if score < 7.0:
            recommendations.append("Proposal needs significant improvement before submission")
        
        # Add revision-based recommendations
        if self.revision_count > 1:
            recommendations.append(f"Proposal went through {self.revision_count} revisions - consider refining approach")
        
        return recommendations or ["Proposal looks good - ready for submission!"]
    
    def get_process_status(self) -> Dict[str, Any]:
        """Get current process status for UI display"""
        state_progress = {
            ProcessState.INITIALIZING: 0.0,
            ProcessState.TRANSLATING_REQUIREMENTS: 0.25,
            ProcessState.VALIDATING_COSTS: 0.5,
            ProcessState.WRITING_PROPOSAL: 0.75,
            ProcessState.REVIEWING_PROPOSAL: 0.9,
            ProcessState.COMPLETED: 1.0,
            ProcessState.FAILED: 0.0
        }
        
        return {
            "current_state": self.state.value,
            "revision_count": self.revision_count,
            "max_revisions": self.max_revisions,
            "progress_percentage": state_progress.get(self.state, 0.0)
        }

class SimpleExpressOrchestrator:
    """Simplified express orchestrator for quick proposal generation"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.llm = self._initialize_llm()
        
    def _initialize_llm(self):
        """Initialize LLM - same as main orchestrator"""
        try:
            if self.config.default_api_provider == APIProvider.OPENAI:
                api_key = os.getenv('OPENAI_API_KEY')
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment variables")
                
                return ChatOpenAI(
                    model=self.config.openai_model,
                    temperature=0.1,
                    api_key=api_key
                )
            else:
                api_key = os.getenv('ANTHROPIC_API_KEY')
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
                
                return ChatAnthropic(
                    model=self.config.claude_model,
                    temperature=0.1,
                    api_key=api_key
                )
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            return self._create_mock_llm()
    
    def _create_mock_llm(self):
        """Create a mock LLM for testing"""
        class MockLLM:
            def invoke(self, prompt):
                class MockResponse:
                    content = "Express mode mock response for testing purposes"
                return MockResponse()
        
        logger.warning("Using mock LLM in express mode - set proper API keys for full functionality")
        return MockLLM()
    
    async def generate_express_proposal(
        self,
        request: ProposalRequest,
        template: ProposalTemplate
    ) -> ProposalOutput:
        """Generate proposal in express mode - minimal validation"""
        
        logger.info(f"Starting express proposal generation for: {request.job_post.title}")
        
        try:
            # Step 1: Quick plan generation
            translator = BusinessTranslatorAgent(self.llm)
            execution_plan = translator.create_execution_plan(
                job_post=request.job_post,
                profile=request.freelancer_profile
            )
            
            # Step 2: Direct proposal writing
            writer = CommercialWriterAgent(self.llm)
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
                reviewer_feedback=["Express mode - limited review performed"],
                quality_score=0.75,  # Default score for express mode
                estimated_win_probability=0.65,  # Conservative estimate
                recommendations=[
                    "Express mode used - consider full validation for important projects",
                    "Review proposal manually before submission"
                ]
            )
            
        except Exception as e:
            logger.error(f"Express proposal generation failed: {str(e)}")
            raise