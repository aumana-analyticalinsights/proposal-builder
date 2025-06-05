# File: app.py - Main Streamlit Application

import streamlit as st
import asyncio
import json
import pandas as pd
import os
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from pathlib import Path

# Import our custom modules
from models.core_models import (
    FreelancerProfile, JobPost, ProposalRequest, ProposalTemplate,
    APIProvider, SystemConfig, ProposalHistory, ProposalStatus
)
from core.simple_orchestrator import SimpleProposalOrchestrator, SimpleExpressOrchestrator
from utils.file_manager import FileManager
from utils.template_manager import TemplateManager
from utils.history_manager import HistoryManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Upwork Proposal Generator",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

class ProposalGeneratorApp:
    """Main Streamlit application class"""
    
    def __init__(self):
        self.file_manager = FileManager()
        self.template_manager = TemplateManager()
        self.history_manager = HistoryManager()
        self.config = self._load_system_config()
        
        # Initialize session state
        self._initialize_session_state()
    
    def _load_system_config(self) -> SystemConfig:
        """Load system configuration"""
        return SystemConfig(
            default_api_provider=APIProvider.OPENAI,
            output_directory="./outputs",
            profile_directory="./profiles",
            template_directory="./templates"
        )
    
    def _initialize_session_state(self):
        """Initialize Streamlit session state variables"""
        if "generated_proposal" not in st.session_state:
            st.session_state.generated_proposal = None
        if "current_execution_plan" not in st.session_state:
            st.session_state.current_execution_plan = None
        if "generation_in_progress" not in st.session_state:
            st.session_state.generation_in_progress = False
        if "sandbox_mode" not in st.session_state:
            st.session_state.sandbox_mode = False
        if "selected_profile" not in st.session_state:
            st.session_state.selected_profile = None
    
    def run(self):
        """Main application entry point"""
        
        # Sidebar navigation
        page = self._render_sidebar()
        
        # Main content area
        if page == "Generator":
            self._render_generator_page()
        elif page == "History":
            self._render_history_page()
        elif page == "Profiles":
            self._render_profiles_page()
        elif page == "Templates":
            self._render_templates_page()
        elif page == "Settings":
            self._render_settings_page()
    
    def _render_sidebar(self) -> str:
        """Render sidebar navigation"""
        
        st.sidebar.title("🚀 Proposal Generator")
        
        # Navigation
        page = st.sidebar.selectbox(
            "Navigate to:",
            ["Generator", "History", "Profiles", "Templates", "Settings"]
        )
        
        st.sidebar.markdown("---")
        
        # System status
        if st.session_state.generation_in_progress:
            st.sidebar.warning("🔄 Generation in progress...")
        else:
            st.sidebar.success("✅ System ready")
        
        # Sandbox mode toggle
        st.session_state.sandbox_mode = st.sidebar.checkbox(
            "🧪 Sandbox Mode",
            value=st.session_state.sandbox_mode,
            help="Don't save outputs to files"
        )
        
        return page
    
    def _render_generator_page(self):
        """Render the main proposal generator page"""
        
        st.title("📝 Upwork Proposal Generator")
        st.markdown("Generate compelling proposals using AI-powered agents")
        
        # Create two columns for better layout
        col1, col2 = st.columns([2, 1])
        
        with col1:
            self._render_input_form()
        
        with col2:
            self._render_quick_actions()
        
        # Results section
        if st.session_state.generated_proposal:
            self._render_results_section()
    
    def _render_input_form(self):
        """Render the main input form"""
        
        st.subheader("📋 Project Details")
        
        # Profile selection
        profiles = self.file_manager.list_profiles()
        if profiles:
            selected_profile_name = st.selectbox(
                "Select Freelancer Profile:",
                options=profiles,
                help="Choose a saved freelancer profile"
            )
            
            if selected_profile_name:
                profile_path = f"./profiles/{selected_profile_name}"
                st.session_state.selected_profile = self.file_manager.load_profile(profile_path)
                
                with st.expander("📊 Profile Summary"):
                    profile = st.session_state.selected_profile
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Name:** {profile.name}")
                        st.write(f"**Rate:** ${profile.hourly_rate}/hour")
                        st.write(f"**Experience:** {profile.experience_years} years")
                    with col2:
                        st.write(f"**Skills:** {', '.join(profile.skills[:3])}...")
                        st.write(f"**Specializations:** {', '.join(profile.specializations[:2])}...")
        else:
            st.warning("No profiles found. Please create a profile in the Profiles section.")
            return
        
        # Job post input
        st.subheader("📋 Job Post")
        job_title = st.text_input("Job Title:", placeholder="e.g., Data Science Project for Customer Analytics")
        job_description = st.text_area(
            "Job Description:",
            height=200,
            placeholder="Paste the complete job description here..."
        )
        
        # Budget and settings
        col1, col2, col3 = st.columns(3)
        with col1:
            budget_min = st.number_input("Budget Min ($):", min_value=0.0, value=1000.0)
        with col2:
            budget_max = st.number_input("Budget Max ($):", min_value=0.0, value=5000.0)
        with col3:
            max_budget = st.number_input("Your Max Budget ($):", min_value=0.0, value=4000.0)
        
        # Advanced settings
        with st.expander("⚙️ Advanced Settings"):
            col1, col2 = st.columns(2)
            with col1:
                api_provider = st.selectbox(
                    "API Provider:",
                    options=[APIProvider.OPENAI.value, APIProvider.CLAUDE.value]
                )
                error_margin = st.slider("Error Margin:", 0.05, 0.30, 0.10, 0.05)
            with col2:
                client_name = st.text_input("Client Name (optional):")
                express_mode = st.checkbox("Express Mode (faster, less validation)")
        
        # Template selection
        templates = self.template_manager.list_templates()
        if templates:
            selected_template = st.selectbox("Proposal Template:", options=templates)
        else:
            st.warning("No templates found. Using default template.")
            selected_template = "default"
        
        # Generation buttons
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button(
                "🚀 Generate Proposal",
                disabled=st.session_state.generation_in_progress or not job_description.strip(),
                use_container_width=True
            ):
                self._generate_proposal(
                    job_title, job_description, budget_min, budget_max, 
                    max_budget, api_provider, error_margin, client_name, 
                    express_mode, selected_template
                )
        
        with col2:
            if st.button(
                "🔄 Regenerate",
                disabled=not st.session_state.generated_proposal,
                use_container_width=True
            ):
                # Regenerate with same parameters
                pass
    
    def _render_quick_actions(self):
        """Render quick actions panel"""
        
        st.subheader("⚡ Quick Actions")
        
        # Template preview
        if st.button("👁️ Preview Template", use_container_width=True):
            st.info("Template preview feature coming soon!")
        
        # Job post validator
        if st.button("✅ Validate Job Post", use_container_width=True):
            st.info("Job post validation feature coming soon!")
        
        # Load from history
        if st.button("📜 Load from History", use_container_width=True):
            st.info("History loading feature coming soon!")
        
        # Quick stats
        st.markdown("---")
        st.subheader("📊 Quick Stats")
        
        # Get recent stats
        history = self.history_manager.get_recent_proposals(5)
        if history:
            accepted = len([p for p in history if p.status == ProposalStatus.ACCEPTED])
            total = len(history)
            win_rate = (accepted / total) * 100 if total > 0 else 0
            
            st.metric("Recent Win Rate", f"{win_rate:.1f}%")
            st.metric("Total Proposals", total)
            
            # Average budget
            avg_budget = sum(p.budget_proposed for p in history) / total
            st.metric("Avg. Budget", f"${avg_budget:.0f}")
        else:
            st.info("No history available")
    
    def _generate_proposal(
        self, job_title: str, job_description: str, budget_min: float, 
        budget_max: float, max_budget: float, api_provider: str, 
        error_margin: float, client_name: str, express_mode: bool, 
        template_name: str
    ):
        """Generate proposal using the orchestrator"""
        
        if not st.session_state.selected_profile:
            st.error("Please select a freelancer profile first.")
            return
        
        # Set generation in progress
        st.session_state.generation_in_progress = True
        
        try:
            # Create job post object
            job_post = JobPost(
                title=job_title,
                description=job_description,
                budget_min=budget_min,
                budget_max=budget_max,
                client_name=client_name if client_name else None
            )
            
            # Create proposal request
            request = ProposalRequest(
                job_post=job_post,
                freelancer_profile=st.session_state.selected_profile,
                template_name=template_name,
                api_provider=APIProvider(api_provider),
                max_budget=max_budget,
                error_margin=error_margin,
                express_mode=express_mode
            )
            
            # Load template
            template = self.template_manager.load_template(template_name)
            
            # Show progress
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            # Generate proposal
            with st.spinner("Generating proposal..."):
                if express_mode:
                    orchestrator = SimpleExpressOrchestrator(self.config)
                    result = asyncio.run(
                        orchestrator.generate_express_proposal(request, template)
                    )
                else:
                    orchestrator = SimpleProposalOrchestrator(self.config)
                    result = asyncio.run(
                        orchestrator.generate_proposal(request, template)
                    )
            
            # Store results
            st.session_state.generated_proposal = result
            st.session_state.current_execution_plan = result.execution_plan
            
            # Save to history if not in sandbox mode
            if not st.session_state.sandbox_mode:
                self._save_proposal_to_history(request, result)
            
            progress_bar.progress(100)
            status_text.success("✅ Proposal generated successfully!")
            
        except Exception as e:
            st.error(f"Error generating proposal: {str(e)}")
            logger.error(f"Proposal generation error: {str(e)}")
        
        finally:
            st.session_state.generation_in_progress = False
    
    def _render_results_section(self):
        """Render the results section with generated proposal"""
        
        st.markdown("---")
        st.subheader("📄 Generated Proposal")
        
        proposal = st.session_state.generated_proposal
        plan = st.session_state.current_execution_plan
        
        # Metrics row
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Quality Score", f"{proposal.quality_score:.1%}")
        with col2:
            st.metric("Win Probability", f"{proposal.estimated_win_probability:.1%}")
        with col3:
            st.metric("Total Cost", f"${plan.total_cost:.0f}")
        with col4:
            st.metric("Total Hours", f"{plan.total_hours:.0f}h")
        
        # Tabs for different views
        tab1, tab2, tab3, tab4 = st.tabs(["📝 Proposal", "📊 Plan & Costs", "💡 Feedback", "📁 Export"])
        
        with tab1:
            # Editable proposal text
            edited_proposal = st.text_area(
                "Proposal Text (editable):",
                value=proposal.proposal_text,
                height=400,
                help="You can edit the proposal before copying or exporting"
            )
            
            # Update button
            if st.button("📝 Update Proposal"):
                st.session_state.generated_proposal.proposal_text = edited_proposal
                st.success("Proposal updated!")
        
        with tab2:
            # Execution plan table
            tasks_data = []
            for task in plan.tasks:
                tasks_data.append({
                    "Task": task.task,
                    "Description": task.description[:100] + "..." if len(task.description) > 100 else task.description,
                    "Role": task.role,
                    "Hours": task.hours,
                    "Rate": f"${task.rate}",
                    "Cost": f"${task.cost:.2f}",
                    "Priority": task.priority.value
                })
            
            df = pd.DataFrame(tasks_data)
            st.dataframe(df, use_container_width=True, height=300)
            
            # Cost breakdown
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("💰 Cost Breakdown")
                st.write(f"**Mandatory Tasks:** ${plan.mandatory_cost:.2f}")
                st.write(f"**Optional Tasks:** ${plan.optional_cost:.2f}")
                st.write(f"**Total Cost:** ${plan.total_cost:.2f}")
            
            with col2:
                # Simple cost visualization
                breakdown_data = {
                    "Category": ["Mandatory", "Optional"],
                    "Cost": [plan.mandatory_cost, plan.optional_cost]
                }
                st.bar_chart(pd.DataFrame(breakdown_data).set_index("Category"))
        
        with tab3:
            # Reviewer feedback and recommendations
            st.subheader("🔍 AI Reviewer Feedback")
            if proposal.reviewer_feedback:
                for feedback in proposal.reviewer_feedback:
                    st.write(f"• {feedback}")
            else:
                st.info("No specific feedback available")
            
            st.subheader("💡 Recommendations")
            for rec in proposal.recommendations:
                st.write(f"• {rec}")
        
        with tab4:
            # Export options
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📋 Copy Proposal", use_container_width=True):
                    st.code(proposal.proposal_text, language="text")
                    st.success("Proposal ready to copy!")
            
            with col2:
                # CSV export for plan
                csv_data = df.to_csv(index=False)
                st.download_button(
                    "📊 Download Plan (CSV)",
                    csv_data,
                    "execution_plan.csv",
                    "text/csv",
                    use_container_width=True
                )
            
            with col3:
                if st.button("💾 Save to History", use_container_width=True):
                    if not st.session_state.sandbox_mode:
                        st.success("Already saved to history!")
                    else:
                        st.info("Enable non-sandbox mode to save")
    
    def _save_proposal_to_history(self, request: ProposalRequest, result):
        """Save proposal to history"""
        history_entry = ProposalHistory(
            id=f"proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            job_title=request.job_post.title,
            client_name=request.job_post.client_name,
            generated_at=datetime.now(),
            status=ProposalStatus.PENDING,
            budget_proposed=result.execution_plan.total_cost
        )
        
        self.history_manager.save_proposal(history_entry, result)
    
    def _render_history_page(self):
        """Render proposal history page"""
        st.title("📜 Proposal History")
        st.info("History management features coming in next update!")
    
    def _render_profiles_page(self):
        """Render freelancer profiles management page"""
        st.title("👤 Freelancer Profiles")
        st.info("Profile management features coming in next update!")
    
    def _render_templates_page(self):
        """Render proposal templates management page"""
        st.title("📋 Proposal Templates")
        st.info("Template management features coming in next update!")
    
    def _render_settings_page(self):
        """Render system settings page"""
        st.title("⚙️ System Settings")
        st.info("Settings management features coming in next update!")

# Utility classes will be implemented in separate files
class FileManager:
    """Handles file operations for profiles, templates, etc."""
    
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
    
    def list_profiles(self) -> List[str]:
        """List available freelancer profiles"""
        try:
            profiles = []
            if self.profiles_dir.exists():
                for file_path in self.profiles_dir.glob("*.json"):
                    profiles.append(file_path.name)
            return sorted(profiles) if profiles else ["example_profile.json"]
        except Exception as e:
            logger.error(f"Error listing profiles: {e}")
            return ["example_profile.json"]
    
    def load_profile(self, filename: str) -> FreelancerProfile:
        """Load a freelancer profile"""
        try:
            file_path = self.profiles_dir / filename
            if file_path.exists():
                import json
                with open(file_path, 'r', encoding='utf-8') as f:
                    profile_data = json.load(f)
                return FreelancerProfile(**profile_data)
            else:
                # Return default profile if file doesn't exist
                return self._get_default_profile()
        except Exception as e:
            logger.error(f"Error loading profile {filename}: {e}")
            return self._get_default_profile()
    
    def _get_default_profile(self) -> FreelancerProfile:
        """Get default profile for testing"""
        return FreelancerProfile(
            name="Default User",
            hourly_rate=50.0,
            skills=["Python", "Machine Learning", "Data Analysis"],
            experience_years=5,
            specializations=["Data Science", "Analytics"],
            portfolio_examples=[
                {
                    "title": "Sample Project",
                    "description": "Example data science project",
                    "results": "Achieved measurable business impact"
                }
            ],
            achievements=["Led successful data science projects", "Expert in Python and ML"]
        )

class TemplateManager:
    """Manages proposal templates"""
    
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager
    
    def list_templates(self) -> List[str]:
        """List available templates"""
        return ["professional", "technical", "creative"]
    
    def load_template(self, name: str) -> ProposalTemplate:
        """Load a template"""
        templates = {
            "professional": ProposalTemplate(
                name="professional",
                sections={
                    "greeting": "Dear {client_name},",
                    "understanding": "I understand you need {project_summary}",
                    "approach": "My approach: {execution_plan}",
                    "experience": "With {experience_years} years of experience...",
                    "pricing": "Investment: ${total_cost} for {total_hours} hours",
                    "closing": "Looking forward to working together.\n\nBest regards,\n{freelancer_name}"
                },
                variables=["client_name", "project_summary", "execution_plan", "experience_years", "total_cost", "total_hours", "freelancer_name"],
                tone="professional"
            ),
            "technical": ProposalTemplate(
                name="technical",
                sections={
                    "greeting": "Hello {client_name},",
                    "technical_analysis": "Technical approach: {execution_plan}",
                    "implementation": "Implementation plan with {total_hours} hours",
                    "pricing": "Development cost: ${total_cost}",
                    "closing": "Ready to start development.\n\n{freelancer_name}"
                },
                variables=["client_name", "execution_plan", "total_hours", "total_cost", "freelancer_name"],
                tone="technical"
            ),
            "creative": ProposalTemplate(
                name="creative",
                sections={
                    "greeting": "Hi {client_name}! 👋",
                    "enthusiasm": "Your project looks amazing!",
                    "approach": "Here's how I'll tackle it: {execution_plan}",
                    "investment": "Investment: ${total_cost}",
                    "excitement": "Let's create something awesome! 🚀\n\n{freelancer_name}"
                },
                variables=["client_name", "execution_plan", "total_cost", "freelancer_name"],
                tone="creative"
            )
        }
        return templates.get(name, templates["professional"])

class HistoryManager:
    """Manages proposal history"""
    
    def __init__(self):
        # Initialize with empty history for now
        self.history_file = Path("history") / "proposals.json"
        self.history_file.parent.mkdir(exist_ok=True)
    
    def get_recent_proposals(self, limit: int) -> List[ProposalHistory]:
        """Get recent proposals"""
        try:
            if self.history_file.exists():
                import json
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    proposals = []
                    for item in data[-limit:]:
                        proposals.append(ProposalHistory(
                            id=item["id"],
                            job_title=item["job_title"],
                            client_name=item.get("client_name"),
                            generated_at=datetime.fromisoformat(item["generated_at"]),
                            status=ProposalStatus(item["status"]),
                            budget_proposed=item["budget_proposed"],
                            final_cost=item.get("final_cost"),
                            notes=item.get("notes")
                        ))
                    return proposals
        except Exception as e:
            logger.error(f"Error loading history: {e}")
        return []
    
    def save_proposal(self, history: ProposalHistory, result):
        """Save proposal to history"""
        try:
            # Load existing history
            history_data = []
            if self.history_file.exists():
                import json
                with open(self.history_file, 'r') as f:
                    history_data = json.load(f)
            
            # Add new proposal
            history_data.append({
                "id": history.id,
                "job_title": history.job_title,
                "client_name": history.client_name,
                "generated_at": history.generated_at.isoformat(),
                "status": history.status.value,
                "budget_proposed": history.budget_proposed,
                "final_cost": history.final_cost,
                "notes": history.notes
            })
            
            # Save back to file
            import json
            with open(self.history_file, 'w') as f:
                json.dump(history_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error saving to history: {e}")

# Main application entry point
if __name__ == "__main__":
    app = ProposalGeneratorApp()
    app.run()