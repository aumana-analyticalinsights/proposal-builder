# File: utils/template_manager.py
import json
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional
import logging

from models.core_models import ProposalTemplate
from utils.file_manager import FileManager

logger = logging.getLogger(__name__)

class TemplateManager:
    """Manages proposal templates with advanced features"""
    
    def __init__(self, file_manager: FileManager):
        self.file_manager = file_manager
        self._ensure_default_templates()
    
    def _ensure_default_templates(self):
        """Create default templates if they don't exist"""
        default_templates = [
            self._create_professional_template(),
            self._create_technical_template(),
            self._create_creative_template()
        ]
        
        for template in default_templates:
            if not (self.file_manager.templates_dir / f"{template.name}.json").exists():
                self.file_manager.save_template(template)
    
    def _create_professional_template(self) -> ProposalTemplate:
        """Create professional template"""
        return ProposalTemplate(
            name="professional",
            sections={
                "greeting": "Dear {client_name},\\n\\nThank you for posting this {job_title} opportunity.",
                "understanding": "After thoroughly reviewing your requirements, I understand you need {project_summary}. This aligns perfectly with my expertise in {relevant_skills}.",
                "approach": "My approach will be systematic and results-driven:\\n\\n{execution_plan_formatted}\\n\\nThis methodology ensures quality deliverables and clear communication throughout the project.",
                "experience": "With {experience_years} years of specialized experience in {primary_specialization}, I have successfully completed similar projects including:\\n{portfolio_highlights}",
                "value_proposition": "What sets me apart:\\n• Proven track record with {achievement_highlight}\\n• Deep expertise in {technical_skills}\\n• Commitment to delivering on time and within budget",
                "pricing": "Based on the project scope, I estimate {total_hours} hours of work at ${hourly_rate} per hour, totaling ${total_cost}. This includes {deliverables_summary}.",
                "timeline": "I can begin immediately and deliver the complete solution within {estimated_timeline}.",
                "closing": "I'm excited about the opportunity to contribute to your project's success. I'd be happy to discuss any questions you might have.\\n\\nLooking forward to hearing from you.\\n\\nBest regards,\\n{freelancer_name}"
            },
            variables=[
                "client_name", "job_title", "project_summary", "relevant_skills",
                "execution_plan_formatted", "experience_years", "primary_specialization",
                "portfolio_highlights", "achievement_highlight", "technical_skills",
                "total_hours", "hourly_rate", "total_cost", "deliverables_summary",
                "estimated_timeline", "freelancer_name"
            ],
            tone="professional"
        )
    
    def _create_technical_template(self) -> ProposalTemplate:
        """Create technical template"""
        return ProposalTemplate(
            name="technical",
            sections={
                "greeting": "Hello {client_name},",
                "technical_understanding": "I've analyzed your {job_title} requirements and identified the key technical challenges:\\n{technical_analysis}",
                "solution_architecture": "Proposed Technical Solution:\\n{technical_approach}\\n\\nTechnology Stack:\\n{technology_stack}",
                "implementation_plan": "Implementation Phases:\\n{execution_plan_formatted}\\n\\nEach phase includes thorough testing and documentation.",
                "technical_expertise": "Relevant Technical Experience:\\n{technical_experience}\\n\\nTools & Technologies: {technical_tools}",
                "deliverables": "Technical Deliverables:\\n{technical_deliverables}\\n\\nAll code will be well-documented, tested, and production-ready.",
                "pricing": "Development Estimate: {total_hours} hours @ ${hourly_rate}/hour = ${total_cost}\\n\\nThis includes development, testing, documentation, and deployment support.",
                "closing": "I'm confident in delivering a robust, scalable solution that meets your technical requirements.\\n\\nReady to start when you are.\\n\\n{freelancer_name}"
            },
            variables=[
                "client_name", "job_title", "technical_analysis", "technical_approach",
                "technology_stack", "execution_plan_formatted", "technical_experience",
                "technical_tools", "technical_deliverables", "total_hours",
                "hourly_rate", "total_cost", "freelancer_name"
            ],
            tone="technical"
        )
    
    def _create_creative_template(self) -> ProposalTemplate:
        """Create creative template"""
        return ProposalTemplate(
            name="creative",
            sections={
                "greeting": "Hi {client_name}! 👋",
                "enthusiasm": "Your {job_title} project caught my attention immediately - it's exactly the kind of challenge I love tackling!",
                "creative_vision": "Here's how I envision bringing your project to life:\\n{creative_approach}\\n\\nThis approach combines creativity with solid technical execution.",
                "unique_perspective": "What makes this exciting:\\n{unique_value_points}\\n\\nI believe in making data tell compelling stories that drive real business impact.",
                "collaborative_approach": "My Process:\\n{execution_plan_formatted}\\n\\nI love collaborating closely with clients to ensure we're creating something truly remarkable together.",
                "portfolio_showcase": "Similar magic I've created:\\n{creative_portfolio_examples}",
                "investment": "Investment for this amazing project: {total_hours} hours of focused creativity at ${hourly_rate}/hour = ${total_cost}",
                "excitement": "I'm genuinely excited about the possibility of working together on this! Let's create something awesome! 🚀\\n\\nCheers,\\n{freelancer_name}"
            },
            variables=[
                "client_name", "job_title", "creative_approach", "unique_value_points",
                "execution_plan_formatted", "creative_portfolio_examples", "total_hours",
                "hourly_rate", "total_cost", "freelancer_name"
            ],
            tone="creative"
        )
    
    def render_template(self, template: ProposalTemplate, variables: Dict[str, Any]) -> str:
        """Render template with provided variables"""
        try:
            # Combine all sections
            full_template = "\\n\\n".join(template.sections.values())
            
            # Replace variables
            rendered = full_template
            for var, value in variables.items():
                placeholder = f"{{{var}}}"
                if placeholder in rendered:
                    rendered = rendered.replace(placeholder, str(value))
            
            # Clean up any unreplaced variables
            import re
            rendered = re.sub(r'\\{[^}]+\\}', '[VARIABLE_NOT_PROVIDED]', rendered)
            
            return rendered
            
        except Exception as e:
            logger.error(f"Error rendering template: {e}")
            return "Error rendering template"
    
    def extract_variables_from_context(self, template: ProposalTemplate, 
                                     job_post, freelancer_profile, 
                                     execution_plan) -> Dict[str, Any]:
        """Extract template variables from context objects"""
        
        variables = {
            # Job-related variables
            "client_name": job_post.client_name or "there",
            "job_title": job_post.title,
            "project_summary": job_post.description[:200] + "..." if len(job_post.description) > 200 else job_post.description,
            
            # Freelancer-related variables
            "freelancer_name": freelancer_profile.name,
            "experience_years": freelancer_profile.experience_years,
            "hourly_rate": freelancer_profile.hourly_rate,
            "primary_specialization": freelancer_profile.specializations[0] if freelancer_profile.specializations else "data science",
            "relevant_skills": ", ".join(freelancer_profile.skills[:5]),
            "technical_skills": ", ".join(freelancer_profile.skills),
            "achievement_highlight": freelancer_profile.achievements[0] if freelancer_profile.achievements else "multiple successful projects",
            
            # Plan-related variables
            "total_hours": execution_plan.total_hours,
            "total_cost": execution_plan.total_cost,
            "execution_plan_formatted": self._format_execution_plan(execution_plan),
            
            # Derived variables
            "estimated_timeline": self._estimate_timeline(execution_plan.total_hours),
            "deliverables_summary": self._summarize_deliverables(execution_plan),
            "portfolio_highlights": self._format_portfolio(freelancer_profile.portfolio_examples[:3]),
            "technology_stack": self._infer_technology_stack(execution_plan),
            "technical_deliverables": self._extract_technical_deliverables(execution_plan)
        }
        
        return variables
    
    def _format_execution_plan(self, plan) -> str:
        """Format execution plan for template"""
        formatted_tasks = []
        for i, task in enumerate(plan.tasks[:5], 1):  # Limit to top 5 tasks
            formatted_tasks.append(f"{i}. {task.task} ({task.hours}h)")
        
        return "\\n".join(formatted_tasks)
    
    def _estimate_timeline(self, total_hours: float) -> str:
        """Estimate project timeline based on hours"""
        if total_hours <= 40:
            return "1-2 weeks"
        elif total_hours <= 80:
            return "2-4 weeks"
        elif total_hours <= 160:
            return "1-2 months"
        else:
            return "2-3 months"
    
    def _summarize_deliverables(self, plan) -> str:
        """Summarize key deliverables"""
        deliverables = set()
        for task in plan.tasks:
            if "analysis" in task.task.lower():
                deliverables.add("detailed analysis")
            if "model" in task.task.lower():
                deliverables.add("trained models")
            if "report" in task.task.lower():
                deliverables.add("comprehensive reports")
            if "dashboard" in task.task.lower():
                deliverables.add("interactive dashboards")
        
        return ", ".join(list(deliverables)[:3]) if deliverables else "project deliverables"
    
    def _format_portfolio(self, examples: List[Dict]) -> str:
        """Format portfolio examples"""
        if not examples:
            return "Multiple successful data science projects with measurable business impact"
        
        formatted = []
        for example in examples:
            title = example.get("title", "Data Science Project")
            result = example.get("results", "Delivered successful outcomes")
            formatted.append(f"• {title}: {result}")
        
        return "\\n".join(formatted)
    
    def _infer_technology_stack(self, plan) -> str:
        """Infer technology stack from execution plan"""
        technologies = set()
        
        for task in plan.tasks:
            task_text = (task.task + " " + task.description).lower()
            
            if any(word in task_text for word in ["python", "pandas", "numpy"]):
                technologies.add("Python")
            if any(word in task_text for word in ["machine learning", "ml", "sklearn"]):
                technologies.add("Scikit-learn")
            if any(word in task_text for word in ["deep learning", "neural", "tensorflow", "pytorch"]):
                technologies.add("TensorFlow/PyTorch")
            if any(word in task_text for word in ["visualization", "dashboard", "plot"]):
                technologies.add("Matplotlib/Plotly")
            if any(word in task_text for word in ["sql", "database", "query"]):
                technologies.add("SQL")
        
        return ", ".join(list(technologies)) if technologies else "Python, Pandas, Scikit-learn"
    
    def _extract_technical_deliverables(self, plan) -> str:
        """Extract technical deliverables from plan"""
        deliverables = []
        
        for task in plan.tasks:
            if task.task.lower().startswith(("develop", "build", "create", "implement")):
                deliverables.append(f"• {task.task}")
        
        return "\\n".join(deliverables[:5]) if deliverables else "• Clean, documented code\\n• Technical documentation\\n• Testing suite"
