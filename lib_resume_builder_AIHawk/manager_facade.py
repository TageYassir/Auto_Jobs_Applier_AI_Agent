from __future__ import annotations

import os
import tempfile
import webbrowser
from pathlib import Path

from .utils import HTML_to_PDF
from src.logging import logger


class FacadeManager:
    def __init__(self, api_key, style_manager, resume_generator, resume_object, log_path):
        lib_directory = Path(__file__).resolve().parent
        self.style_manager = style_manager
        self.style_manager.set_styles_directory(lib_directory / "resume_style")
        self.resume_generator = resume_generator
        self.resume_generator.set_resume_object(resume_object)
        self.selected_style = None
        self.log_path = Path(log_path)
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key

    def prompt_user(self, choices: list[str], message: str) -> str:
        print(message)
        for index, choice in enumerate(choices, start=1):
            print(f"{index}. {choice}")
        while True:
            selection = input("Select an option: ").strip()
            if selection.isdigit() and 1 <= int(selection) <= len(choices):
                return choices[int(selection) - 1]
            if selection in choices:
                return selection
            print("Invalid selection, try again.")

    def prompt_for_url(self, message: str) -> str:
        return input(f"{message}: ").strip()

    def prompt_for_text(self, message: str) -> str:
        return input(f"{message}: ").strip()

    def choose_style(self):
        styles = self.style_manager.get_styles()
        if not styles:
            logger.warning("No styles available.")
            return None
        final_style_choice = "Create your resume style in CSS"
        formatted_choices = self.style_manager.format_choices(styles)
        formatted_choices.append(final_style_choice)
        selected_choice = self.prompt_user(formatted_choices, "Which style would you like to adopt?")
        if selected_choice == final_style_choice:
            tutorial_url = "https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk/blob/main/how_to_contribute/web_designer.md"
            print("\nOpening tutorial in your browser...")
            webbrowser.open(tutorial_url)
            raise SystemExit(0)
        self.selected_style = selected_choice.split(" (")[0]
        return self.selected_style

    def pdf_base64(self, job_description_url=None, job_description_text=None):
        if job_description_url is not None and job_description_text is not None:
            raise ValueError("Exactly one of job_description_url or job_description_text must be provided.")

        if self.selected_style is None:
            raise ValueError("Choose a style before generating the PDF.")

        style_path = self.style_manager.get_style_path(self.selected_style)

        with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".html", encoding="utf-8") as temp_html_file:
            temp_html_path = temp_html_file.name
            if job_description_url is None and job_description_text is None:
                self.resume_generator.create_resume(style_path, temp_html_path)
            elif job_description_url is not None:
                self.resume_generator.create_resume_job_description_url(style_path, job_description_url, temp_html_path)
            else:
                self.resume_generator.create_resume_job_description_text(style_path, job_description_text, temp_html_path)

        pdf_base64 = HTML_to_PDF(temp_html_path)
        os.remove(temp_html_path)
        return pdf_base64
