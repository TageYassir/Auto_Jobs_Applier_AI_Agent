from __future__ import annotations

import re
import textwrap
from datetime import date
from typing import Optional

from config import JOB_SUITABILITY_SCORE
from src.ai_hawk.llm import prompts
from src.ai_hawk.llm.provider import generate_text, is_llm_available, summarize_or_none
from src.job import Job
from src.logging import logger


class GPTAnswerer:
    def __init__(self, config, llm_api_key=None):
        self.config = config or {}
        self.manual_answers = self.config.get("manual_answers", {}) if isinstance(self.config, dict) else {}
        self.job = None
        self.resume = None
        self.job_application_profile = None

    def set_resume(self, resume):
        self.resume = resume

    def set_job(self, job: Job):
        self.job = job
        if job and job.description:
            summary = self.summarize_job_description(job.description)
            job.set_summarize_job_description(summary or "")

    def set_job_application_profile(self, job_application_profile):
        self.job_application_profile = job_application_profile

    @staticmethod
    def _clean_output(output: Optional[str]) -> str:
        if not output:
            return ""
        return output.replace("*", "").replace("#", "").strip()

    @staticmethod
    def _normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()

    def _manual_lookup(self, question: str) -> Optional[str]:
        normalized_question = self._normalize(question)
        for key, value in self.manual_answers.items():
            if self._normalize(str(key)) in normalized_question:
                return str(value)
        return None

    def _resume_text(self) -> str:
        return str(self.resume or "")

    def _profile_text(self) -> str:
        return str(self.job_application_profile or "")

    def summarize_job_description(self, text: str) -> str:
        if not text:
            return ""
        output = summarize_or_none(text)
        return self._clean_output(output) if output else ""

    def _section_from_question(self, question: str) -> str:
        prompt = textwrap.dedent(prompts.determine_section_template).format(question=question)
        output = generate_text(prompt, system="Return the most relevant resume section only.", temperature=0.0, max_tokens=24)
        output = self._clean_output(output).lower()
        if not output:
            return ""
        mapping = {
            "personal information": "personal_information",
            "self identification": "self_identification",
            "legal authorization": "legal_authorization",
            "work preferences": "work_preferences",
            "education details": "education_details",
            "experience details": "experience_details",
            "projects": "projects",
            "availability": "availability",
            "salary expectations": "salary_expectations",
            "certifications": "certifications",
            "languages": "languages",
            "interests": "interests",
            "cover letter": "cover_letter",
        }
        for key, value in mapping.items():
            if key in output:
                return value
        return ""

    def _field_value_from_resume(self, section_name: str, question: str) -> str:
        resume = self.resume
        if resume is None:
            return ""
        question_text = self._normalize(question)
        personal = getattr(resume, "personal_information", None)
        if section_name == "personal_information" and personal:
            fields = {
                "email": getattr(personal, "email", ""),
                "github": getattr(personal, "github", ""),
                "linkedin": getattr(personal, "linkedin", ""),
                "phone": f"{getattr(personal, 'phone_prefix', '')}{getattr(personal, 'phone', '')}".strip(),
                "city": getattr(personal, "city", ""),
                "country": getattr(personal, "country", ""),
                "name": f"{getattr(personal, 'name', '')} {getattr(personal, 'surname', '')}".strip(),
                "surname": getattr(personal, "surname", ""),
                "zip code": getattr(personal, "zip_code", ""),
            }
            for key, value in fields.items():
                if key in question_text and value:
                    return str(value)
            return self._clean_output(str(personal))

        if section_name == "self_identification" and getattr(resume, "self_identification", None):
            return self._clean_output(str(resume.self_identification))

        if section_name == "legal_authorization" and getattr(resume, "legal_authorization", None):
            return self._clean_output(str(resume.legal_authorization))

        if section_name == "work_preferences" and getattr(resume, "work_preferences", None):
            return self._clean_output(str(resume.work_preferences))

        if section_name == "availability" and getattr(resume, "availability", None):
            return self._clean_output(str(resume.availability))

        if section_name == "salary_expectations" and getattr(resume, "salary_expectations", None):
            return self._clean_output(str(resume.salary_expectations))

        if section_name == "languages" and getattr(resume, "languages", None):
            return self._clean_output(str(resume.languages))

        if section_name == "certifications" and getattr(resume, "certifications", None):
            return self._clean_output(str(resume.certifications))

        if section_name == "projects" and getattr(resume, "projects", None):
            return self._clean_output(str(resume.projects))

        if section_name == "interests" and getattr(resume, "interests", None):
            return self._clean_output(str(resume.interests))

        if section_name in {"education_details", "experience_details"}:
            return self._clean_output(str(getattr(resume, section_name, "")))

        return ""

    def answer_question_textual_wide_range(self, question: str) -> str:
        section_name = self._section_from_question(question)
        if not section_name:
            manual = self._manual_lookup(question)
            return manual or "MANUAL_REQUIRED"

        if section_name == "cover_letter":
            if not self.job:
                return ""
            prompt = textwrap.dedent(prompts.coverletter_template).format(
                company=self.job.company or "Unknown Company",
                job_description=self.job.description or "",
                resume=self._resume_text(),
            )
            output = generate_text(prompt, system="Write a concise cover letter.", temperature=0.4, max_tokens=500)
            return self._clean_output(output) if output else ""

        manual = self._manual_lookup(question)
        if manual:
            return manual

        fallback = self._field_value_from_resume(section_name, question)
        if fallback:
            return fallback

        prompt_map = {
            "personal_information": prompts.personal_information_template,
            "self_identification": prompts.self_identification_template,
            "legal_authorization": prompts.legal_authorization_template,
            "work_preferences": prompts.work_preferences_template,
            "education_details": prompts.education_details_template,
            "experience_details": prompts.experience_details_template,
            "projects": prompts.projects_template,
            "availability": prompts.availability_template,
            "salary_expectations": prompts.salary_expectations_template,
            "certifications": prompts.certifications_template,
            "languages": prompts.languages_template,
            "interests": prompts.interests_template,
        }
        template = prompt_map.get(section_name)
        if not template:
            return "MANUAL_REQUIRED"

        prompt = textwrap.dedent(template).format(
            resume_section=f"{self._resume_text()}\n{self._profile_text()}",
            question=question,
            resume=self._resume_text(),
            job_application_profile=self._profile_text(),
            resume_educations=getattr(self.resume, "education_details", ""),
            resume_jobs=getattr(self.resume, "experience_details", ""),
            resume_projects=getattr(self.resume, "projects", ""),
        )
        output = generate_text(prompt, system="Answer the question directly and concisely.", temperature=0.2, max_tokens=120)
        return self._clean_output(output) if output else fallback or "MANUAL_REQUIRED"

    def answer_question_numeric(self, question: str, default_experience: str = 3) -> str:
        manual = self._manual_lookup(question)
        if manual and manual.isdigit():
            return manual
        prompt = textwrap.dedent(prompts.numeric_question_template).format(
            resume_educations=getattr(self.resume, "education_details", ""),
            resume_jobs=getattr(self.resume, "experience_details", ""),
            resume_projects=getattr(self.resume, "projects", ""),
            question=question,
        )
        output = generate_text(prompt, system="Return a single numeric value only.", temperature=0.0, max_tokens=32)
        output = self._clean_output(output)
        match = re.search(r"\d+", output)
        if match:
            return match.group(0)
        logger.warning("Numeric LLM answer unavailable. Falling back to default/manual value.")
        return str(default_experience)

    def extract_number_from_string(self, output_str):
        numbers = re.findall(r"\d+", output_str)
        if numbers:
            return str(numbers[0])
        raise ValueError("No numbers found in the string")

    def answer_question_from_options(self, question: str, options: list[str]) -> str:
        manual = self._manual_lookup(question)
        if manual and manual in options:
            return manual
        prompt = textwrap.dedent(prompts.options_template).format(
            resume=self._resume_text(),
            job_application_profile=self._profile_text(),
            question=question,
            options=options,
        )
        output = generate_text(prompt, system="Choose one option only.", temperature=0.0, max_tokens=32)
        output = self._clean_output(output)
        for option in options:
            if option.lower() in output.lower():
                return option
        for option in options:
            if option and "select" not in option.lower() and "none" not in option.lower() and "choose" not in option.lower():
                return option
        return options[0] if options else "MANUAL_REQUIRED"

    def resume_or_cover(self, phrase: str) -> str:
        manual = self._manual_lookup(phrase)
        if manual in {"resume", "cover"}:
            return manual
        prompt = textwrap.dedent(prompts.resume_or_cover_letter_template).format(phrase=phrase)
        output = generate_text(prompt, system="Return resume or cover only.", temperature=0.0, max_tokens=8)
        output = self._clean_output(output).lower()
        if "cover" in output:
            return "cover"
        return "resume"

    def answer_question_date(self):
        if is_llm_available():
            return date.today()
        logger.warning("LLM unavailable for date question. Using today's date as fallback.")
        return date.today()

    def is_job_suitable(self):
        if not self.job:
            return True
        if not is_llm_available():
            logger.warning("LLM unavailable (Ollama). Skipping suitability check and continuing.")
            return True
        prompt = textwrap.dedent(prompts.is_relavant_position_template).format(
            job_description=self.job.description or "",
            resume=self._resume_text(),
        )
        output = generate_text(prompt, system="Return Score and Reasoning only.", temperature=0.0, max_tokens=120)
        output = self._clean_output(output)
        score_match = re.search(r"Score:\s*(\d+)", output, re.IGNORECASE)
        if not score_match:
            logger.warning("Failed to parse suitability score. Continuing with application.")
            return True
        return int(score_match.group(1)) >= JOB_SUITABILITY_SCORE
