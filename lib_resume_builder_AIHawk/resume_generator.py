from __future__ import annotations

import html
from pathlib import Path
from string import Template

from src.ai_hawk.llm.provider import generate_text, is_llm_available
from src.logging import logger

from .resume import Resume
from .utils import HTML_to_PDF


class ResumeGenerator:
    def __init__(self):
        self.resume_object = None

    def set_resume_object(self, resume_object):
        self.resume_object = resume_object

    def _read_style(self, style_path: Path) -> str:
        return style_path.read_text(encoding="utf-8")

    def _section_items(self, section):
        if not section:
            return []
        if isinstance(section, list):
            return section
        return [section]

    def _text(self, value):
        if value is None:
            return ""
        if hasattr(value, "__dict__"):
            pairs = []
            for key, item in vars(value).items():
                if isinstance(item, list):
                    item = ", ".join(str(v) for v in item)
                pairs.append(f"{key.replace('_', ' ').title()}: {item}")
            return " | ".join(pairs)
        return str(value)

    def _render_html(self, tailored_summary: str = "") -> str:
        resume = self.resume_object
        if resume is None:
            raise ValueError("Resume object is not set.")

        header = resume.personal_information
        style_css = ""
        summary_html = ""
        if tailored_summary:
            summary_html = f"<section><h2>Tailored Summary</h2><p>{html.escape(tailored_summary)}</p></section>"

        parts = [
            "<html><head><meta charset='utf-8'>",
            f"<style>{style_css}</style>",
            "</head><body>",
        ]

        if header:
            parts.append("<header>")
            full_name = f"{getattr(header, 'name', '')} {getattr(header, 'surname', '')}".strip()
            parts.append(f"<h1>{html.escape(full_name)}</h1>")
            contact_bits = [
                getattr(header, 'city', ''),
                getattr(header, 'country', ''),
                getattr(header, 'phone_prefix', ''),
                getattr(header, 'phone', ''),
                getattr(header, 'email', ''),
                getattr(header, 'linkedin', ''),
                getattr(header, 'github', ''),
            ]
            parts.append(f"<p>{html.escape(' | '.join(str(bit) for bit in contact_bits if bit))}</p>")
            parts.append("</header>")

        if summary_html:
            parts.append(summary_html)

        def render_section(title, items, formatter):
            if not items:
                return
            parts.append(f"<section><h2>{html.escape(title)}</h2>")
            for item in items:
                parts.append(formatter(item))
            parts.append("</section>")

        render_section(
            "Education",
            self._section_items(resume.education_details),
            lambda item: (
                "<div class='entry'>"
                f"<h3>{html.escape(self._text(getattr(item, 'institution', '')))}</h3>"
                f"<p>{html.escape(self._text(getattr(item, 'education_level', '')))}"
                f"{(' - ' + self._text(getattr(item, 'field_of_study', ''))) if getattr(item, 'field_of_study', None) else ''}"
                f"{(' | ' + self._text(getattr(item, 'year_of_completion', ''))) if getattr(item, 'year_of_completion', None) else ''}</p>"
                "</div>"
            ),
        )

        render_section(
            "Experience",
            self._section_items(resume.experience_details),
            lambda item: (
                "<div class='entry'>"
                f"<h3>{html.escape(self._text(getattr(item, 'position', '')))} - {html.escape(self._text(getattr(item, 'company', '')))}</h3>"
                f"<p>{html.escape(self._text(getattr(item, 'employment_period', '')))} | {html.escape(self._text(getattr(item, 'location', '')))} | {html.escape(self._text(getattr(item, 'industry', '')))}</p>"
                "</div>"
            ),
        )

        render_section(
            "Projects",
            self._section_items(resume.projects),
            lambda item: (
                "<div class='entry'>"
                f"<h3>{html.escape(self._text(getattr(item, 'name', '')))}</h3>"
                f"<p>{html.escape(self._text(getattr(item, 'description', '')))}</p>"
                f"<p>{html.escape(self._text(getattr(item, 'link', '')))}</p>"
                "</div>"
            ),
        )

        render_section(
            "Certifications",
            self._section_items(resume.certifications),
            lambda item: f"<div class='entry'><p>{html.escape(self._text(getattr(item, 'name', item)))}{(' - ' + html.escape(self._text(getattr(item, 'description', '')))) if hasattr(item, 'description') else ''}</p></div>",
        )

        render_section(
            "Languages",
            self._section_items(resume.languages),
            lambda item: f"<div class='entry'><p>{html.escape(self._text(getattr(item, 'language', item)))}{(' - ' + html.escape(self._text(getattr(item, 'proficiency', '')))) if hasattr(item, 'proficiency') else ''}</p></div>",
        )

        if resume.interests:
            parts.append("<section><h2>Interests</h2><p>")
            parts.append(html.escape(", ".join(str(item) for item in resume.interests)))
            parts.append("</p></section>")

        parts.append("</body></html>")
        return "\n".join(parts)

    def _create_resume(self, style_path, temp_html_path, tailored_summary: str = ""):
        template = Template("$markdown")
        style_css = self._read_style(Path(style_path))
        message = template.substitute(markdown=self._render_html(tailored_summary).replace("<style></style>", f"<style>{style_css}</style>"), style_path=style_path)
        with open(temp_html_path, "w", encoding="utf-8") as temp_file:
            temp_file.write(message)

    def create_resume(self, style_path, temp_html_file):
        self._create_resume(style_path, temp_html_file)

    def create_resume_job_description_url(self, style_path: str, url_job_description: str, temp_html_path):
        try:
            import httpx

            response = httpx.get(url_job_description, timeout=20)
            response.raise_for_status()
            job_description_text = response.text
        except Exception as exc:
            logger.warning(f"Failed to fetch job description URL. Falling back to base resume. {exc}")
            return self.create_resume(style_path, temp_html_path)
        return self.create_resume_job_description_text(style_path, job_description_text, temp_html_path)

    def create_resume_job_description_text(self, style_path: str, job_description_text: str, temp_html_path):
        if not is_llm_available():
            logger.warning(
                "LLM unavailable (Ollama). Falling back to base resume generation. If you want to continue manually, upload your own CV with --resume."
            )
            return self.create_resume(style_path, temp_html_path)

        prompt = (
            "You are tailoring a resume for a specific job description. "
            "Write a concise 3-5 bullet summary of the candidate's fit for the role. "
            "Use only information that can be inferred from the resume and job description. "
            "Return plain text only.\n\n"
            f"JOB DESCRIPTION:\n{job_description_text}\n"
        )
        tailored_summary = generate_text(prompt, system="You are a concise resume tailor.", temperature=0.2, max_tokens=220)
        if not tailored_summary:
            logger.warning("LLM tailoring failed. Falling back to base resume generation.")
            return self.create_resume(style_path, temp_html_path)

        self._create_resume(style_path, temp_html_path, tailored_summary=tailored_summary)
