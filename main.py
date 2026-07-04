import os
import re
import sys
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from lib_resume_builder_AIHawk import Resume, FacadeManager, ResumeGenerator, StyleManager
from typing import Optional
from constants import PLAIN_TEXT_RESUME_YAML, SECRETS_YAML, WORK_PREFERENCES_YAML
from src.utils.chrome_utils import chrome_browser_options
from src.ai_hawk.llm.provider import is_llm_available

from src.job_application_profile import JobApplicationProfile
from src.logging import logger

# Suppress stderr only during specific operations
original_stderr = sys.stderr

# Add the src directory to the Python path
sys.path.append(str(Path(__file__).resolve().parent / 'src'))

from src.ai_hawk.authenticator import get_authenticator
from src.ai_hawk.bot_facade import AIHawkBotFacade
from src.ai_hawk.job_manager import AIHawkJobManager
from src.ai_hawk.llm.llm_manager import GPTAnswerer


class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
    
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")

    @staticmethod
    def validate_config(config_yaml_path: Path) -> dict:
        parameters = ConfigValidator.validate_yaml_file(config_yaml_path)
        required_keys = {
            'remote': bool,
            'experience_level': dict,
            'job_types': dict,
            'date': dict,
            'positions': list,
            'locations': list,
            'location_blacklist': list,
            'distance': int,
            'company_blacklist': list,
            'title_blacklist': list,
        }

        for key, expected_type in required_keys.items():
            if key not in parameters:
                if key in ['company_blacklist', 'title_blacklist', 'location_blacklist']:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Missing or invalid key '{key}' in config file {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                if key in ['company_blacklist', 'title_blacklist', 'location_blacklist'] and parameters[key] is None:
                    parameters[key] = []
                else:
                    raise ConfigError(f"Invalid type for key '{key}' in config file {config_yaml_path}. Expected {expected_type}.")

        # Validate experience levels, ensure they are boolean
        experience_levels = ['internship', 'entry', 'associate', 'mid_senior_level', 'director', 'executive']
        for level in experience_levels:
            if not isinstance(parameters['experience_level'].get(level), bool):
                raise ConfigError(f"Experience level '{level}' must be a boolean in config file {config_yaml_path}")

        # Validate job types, ensure they are boolean
        job_types = ['full_time', 'contract', 'part_time', 'temporary', 'internship', 'other', 'volunteer']
        for job_type in job_types:
            if not isinstance(parameters['job_types'].get(job_type), bool):
                raise ConfigError(f"Job type '{job_type}' must be a boolean in config file {config_yaml_path}")

        # Validate date filters
        date_filters = ['all_time', 'month', 'week', '24_hours']
        for date_filter in date_filters:
            if not isinstance(parameters['date'].get(date_filter), bool):
                raise ConfigError(f"Date filter '{date_filter}' must be a boolean in config file {config_yaml_path}")

        # Validate positions and locations as lists of strings
        if not all(isinstance(pos, str) for pos in parameters['positions']):
            raise ConfigError(f"'positions' must be a list of strings in config file {config_yaml_path}")
        if not all(isinstance(loc, str) for loc in parameters['locations']):
            raise ConfigError(f"'locations' must be a list of strings in config file {config_yaml_path}")

        # Validate distance
        approved_distances = {0, 5, 10, 25, 50, 100}
        if parameters['distance'] not in approved_distances:
            raise ConfigError(f"Invalid distance value in config file {config_yaml_path}. Must be one of: {approved_distances}")

        # Ensure blacklists are lists
        for blacklist in ['company_blacklist', 'title_blacklist','location_blacklist']:
            if not isinstance(parameters.get(blacklist), list):
                raise ConfigError(f"'{blacklist}' must be a list in config file {config_yaml_path}")
            if parameters[blacklist] is None:
                parameters[blacklist] = []

        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> dict:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        if secrets is None:
            secrets = {}
        if not isinstance(secrets, dict):
            raise ConfigError(f"Secrets file must contain a YAML mapping in {secrets_yaml_path}")
        return secrets

class FileManager:
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = [SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML]
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"Missing files in the data folder: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / SECRETS_YAML, app_data_folder / WORK_PREFERENCES_YAML, app_data_folder / PLAIN_TEXT_RESUME_YAML, output_folder)

    @staticmethod
    def file_paths_to_dict(resume_file: Optional[Path], plain_text_resume_file: Optional[Path]) -> dict:
        if not plain_text_resume_file or not plain_text_resume_file.exists():
            raise FileNotFoundError("Plain text resume file is required and must be provided via CLI argument. CLI argument.")

        result = {'plainTextResume': plain_text_resume_file}

        if resume_file:
            if not resume_file.exists():
                raise FileNotFoundError(f"Resume file not found: {resume_file}")
            result['resume'] = resume_file

        return result

def init_browser() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(parameters):
    try:
        style_manager = StyleManager()
        resume_generator = ResumeGenerator()
        with open(parameters['uploads']['plainTextResume'], "r", encoding='utf-8') as file:
            plain_text_resume = file.read()
        resume_object = Resume(plain_text_resume)
        resume_generator_manager = FacadeManager(None, style_manager, resume_generator, resume_object, Path("data_folder/output"))
        
        # If the user didn't provide --resume, ask them to choose a style OR upload a CV
        if 'resume' not in parameters['uploads']:
            # Show the same menu options but add an "Upload" choice
            print("\nWhich style would you like to adopt?")
            print("1. Clean Blue (style author -> https://github.com/samodum)")
            print("2. Default (style author -> https://github.com/krishnavalliappan)")
            print("3. Modern Blue (style author -> https://github.com/josylad)")
            print("4. Create your resume style in CSS")
            print("5. Upload your own CV (PDF)")
            choice = input("Enter your choice (1-5): ").strip()
            if choice == "5":
                # Prompt for a PDF path
                while True:
                    user_path = input("Enter the full path to your CV PDF file: ").strip()
                    if not user_path:
                        print("No path entered. Please try again.")
                        continue
                    resume_path = Path(user_path)
                    if not resume_path.exists():
                        print(f"File not found: {resume_path}")
                        continue
                    if resume_path.suffix.lower() != ".pdf":
                        print("Only PDF files are accepted.")
                        continue
                    # Valid file – store it in parameters and skip generation
                    parameters['uploads']['resume'] = resume_path
                    print("Your CV will be uploaded instead of generating a new one.\n")
                    break
            else:
                # Let the original style manager handle the choice (1-4)
                # We can pass the choice number if the FacadeManager supports it,
                # otherwise call the original choose_style() which will prompt again.
                # If FacadeManager.choose_style() doesn't accept a direct choice,
                # we can call it directly (it will re-ask the same menu).
                resume_generator_manager.choose_style()   # This will show the same 1-4 menu
        
        job_application_profile_object = JobApplicationProfile(plain_text_resume)

        if not is_llm_available():
            logger.warning(
                "LLM unavailable (Ollama). AI features will fall back to manual/skip mode. "
                "If you want to upload your own CV instead of generating one, use the --resume option."
            )
        
        browser = init_browser()
        login_component = get_authenticator(driver=browser, platform='linkedin')
        apply_component = AIHawkJobManager(browser)
        gpt_answerer_component = GPTAnswerer(parameters)
        bot = AIHawkBotFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        bot.set_parameters(parameters)
        bot.start_login()
        if (parameters['collectMode'] == True):
            logger.info('Collecting')
            bot.start_collect_data()
        else:
            logger.info('Applying')
            bot.start_apply()
    except WebDriverException as e:
        logger.error(f"WebDriver error occurred: {e}")
    except Exception as e:
        raise RuntimeError(f"Error running the bot: {str(e)}")


@click.command()
@click.option('--resume', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), help="Path to the resume PDF file")
@click.option('--collect', is_flag=True, help="Only collects data job information into data.json file")
def main(collect: bool = False, resume: Optional[Path] = None):
    try:
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)
        
        parameters = ConfigValidator.validate_config(config_file)
        secrets = ConfigValidator.validate_secrets(secrets_file)
        
        parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        parameters['outputFileDirectory'] = output_folder
        parameters['collectMode'] = collect
        parameters['manual_answers'] = secrets.get('manual_answers', {}) or {}
        
        create_and_run_bot(parameters)
    except ConfigError as ce:
        logger.error(f"Configuration error: {str(ce)}")
        logger.error(f"Refer to the configuration guide for troubleshooting: https://github.com/feder-cr/Auto_Jobs_Applier_AIHawk?tab=readme-ov-file#configuration {str(ce)}")

    except FileNotFoundError as fnf:
        logger.error(f"File not found: {str(fnf)}")
        logger.error("Ensure all required files are present in the data folder.")
    except RuntimeError as re:
        logger.error(f"Runtime error: {str(re)}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    main()
