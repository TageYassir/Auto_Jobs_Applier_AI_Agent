from __future__ import annotations

from types import SimpleNamespace

from src.ai_hawk.llm import llm_manager
from src.job import Job


class DummyResume:
    def __init__(self):
        self.personal_information = SimpleNamespace(
            name="Jane",
            surname="Doe",
            city="Dublin",
            country="Ireland",
            phone_prefix="+1",
            phone="5551234567",
            email="jane@example.com",
            github="https://github.com/janedoe",
            linkedin="https://www.linkedin.com/in/janedoe/",
            zip_code="12345",
        )
        self.education_details = []
        self.experience_details = []
        self.projects = []
        self.certifications = []
        self.languages = []
        self.interests = []
        self.self_identification = None
        self.legal_authorization = None
        self.work_preferences = None
        self.availability = None
        self.salary_expectations = None

    def __str__(self):
        return "DummyResume"


def test_textual_answer_uses_manual_mapping(monkeypatch):
    monkeypatch.setattr(llm_manager, "generate_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_manager, "is_llm_available", lambda: False)

    answerer = llm_manager.GPTAnswerer({"manual_answers": {"email": "jane@example.com"}})
    answerer.set_resume(DummyResume())

    assert answerer.answer_question_textual_wide_range("What is your email address?") == "jane@example.com"


def test_options_answer_falls_back_to_valid_option(monkeypatch):
    monkeypatch.setattr(llm_manager, "generate_text", lambda *args, **kwargs: None)
    monkeypatch.setattr(llm_manager, "is_llm_available", lambda: False)

    answerer = llm_manager.GPTAnswerer({})
    answerer.set_resume(DummyResume())

    assert answerer.answer_question_from_options("Are you remote?", ["Select an option", "Yes", "No"]) == "Yes"


def test_job_suitability_skips_when_llm_unavailable(monkeypatch):
    monkeypatch.setattr(llm_manager, "is_llm_available", lambda: False)
    answerer = llm_manager.GPTAnswerer({})
    answerer.set_resume(DummyResume())
    answerer.set_job(Job(title="Engineer", company="Example", description="Example description"))

    assert answerer.is_job_suitable() is True
