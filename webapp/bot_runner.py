import sys
from pathlib import Path
import threading
import time
from datetime import datetime
import yaml

# ---- Absolute paths to project root ----
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / 'src'))

# ---- Original bot imports ----
from src.ai_hawk.bot_facade import AIHawkBotFacade
from src.ai_hawk.job_manager import AIHawkJobManager
from src.ai_hawk.authenticator import get_authenticator
from src.ai_hawk.llm.llm_manager import GPTAnswerer
from src.job_application_profile import JobApplicationProfile
from lib_resume_builder_AIHawk import Resume, FacadeManager, ResumeGenerator, StyleManager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from src.utils.chrome_utils import chrome_browser_options
from src.logging import logger

# ---- Constants (file paths) ----
from constants import SECRETS_YAML, WORK_PREFERENCES_YAML, PLAIN_TEXT_RESUME_YAML

# ---- Webapp models (import models only, db will be obtained from app context) ----
from webapp.models import Run, ApplicationLog, Configuration, ResumeContent


def db_log_callback(app, run_id, job, status, reason=None):
    with app.app_context():
        db = app.extensions['sqlalchemy']
        log = ApplicationLog(
            run_id=run_id,
            job_title=job.title,
            company=job.company,
            link=job.link,
            location=job.location,
            status=status,
            reason=reason
        )
        db.session.add(log)
        db.session.commit()


class BotThread(threading.Thread):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.stop_event = threading.Event()
        self.driver = None

    def run(self):
        with self.app.app_context():
            db = self.app.extensions['sqlalchemy']
            run = Run(start_time=datetime.utcnow(), status='running')
            db.session.add(run)
            db.session.commit()
            run_id = run.id

            try:
                self._execute_bot(run_id)
            except Exception as e:
                logger.error(f"Bot thread error: {e}")
                run = db.session.get(Run, run_id)
                run.status = 'error'
                run.notes = str(e)
                run.end_time = datetime.utcnow()
                db.session.commit()
            finally:
                if self.driver:
                    try:
                        self.driver.quit()
                    except:
                        pass

    def _execute_bot(self, run_id):
        # 1. Load base parameters – use absolute paths inside project_root/data_folder
        data_folder = project_root / 'data_folder'
        with open(data_folder / WORK_PREFERENCES_YAML, 'r') as f:
            parameters = yaml.safe_load(f)

        db = self.app.extensions['sqlalchemy']

        # 2. DB configuration overrides
        cfg = db.session.get(Configuration, 1)
        if cfg:
            if cfg.manual_position:
                parameters['positions'] = [p.strip() for p in cfg.manual_position.split(',') if p.strip()]
            if cfg.countries:
                parameters['locations'] = [c.strip() for c in cfg.countries.split(',') if c.strip()]
            if cfg.contract_types:
                parameters['job_types'] = {jt: (jt in cfg.contract_types) for jt in parameters.get('job_types', {})}
            if cfg.experience_level is not None:
                parameters['experience_level'] = cfg.experience_level
            parameters['remote'] = cfg.remote
            parameters['hybrid'] = cfg.hybrid
            parameters['onsite'] = cfg.onsite
            parameters['distance'] = cfg.distance
            if cfg.date_filter:
                parameters['date'] = {k: (k == cfg.date_filter) for k in parameters.get('date', {})}
            parameters['apply_once_at_company'] = cfg.apply_once_at_company
            if cfg.company_blacklist:
                parameters['company_blacklist'] = [x.strip() for x in cfg.company_blacklist.split(',') if x.strip()]
            if cfg.title_blacklist:
                parameters['title_blacklist'] = [x.strip() for x in cfg.title_blacklist.split(',') if x.strip()]
            if cfg.location_blacklist:
                parameters['location_blacklist'] = [x.strip() for x in cfg.location_blacklist.split(',') if x.strip()]
            # Use uploaded CV if available
            if cfg.cv_path:
                if 'uploads' not in parameters:
                    parameters['uploads'] = {}
                parameters['uploads']['resume'] = Path(cfg.cv_path)

        # 3. Resume content
        resume_db = db.session.get(ResumeContent, 1)
        if resume_db and resume_db.plain_text_yaml.strip():
            plain_text_resume = resume_db.plain_text_yaml
        else:
            with open(data_folder / PLAIN_TEXT_RESUME_YAML, 'r') as f:
                plain_text_resume = f.read()

        resume_object = Resume(plain_text_resume)
        job_application_profile = JobApplicationProfile(plain_text_resume)

        # 4. Browser
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)

        # 5. Components
        login_component = get_authenticator(driver=self.driver, platform='linkedin')
        apply_component = AIHawkJobManager(self.driver)
        apply_component.stop_event = self.stop_event
        apply_component.run_id = run_id
        log_func = lambda run_id, job, status, reason=None: db_log_callback(self.app, run_id, job, status, reason)
        apply_component.set_db_logger(log_func)

        gpt_answerer = GPTAnswerer(parameters)
        resume_generator_manager = None  # headless

        bot = AIHawkBotFacade(login_component, apply_component)
        bot.set_job_application_profile_and_resume(job_application_profile, resume_object)
        bot.set_gpt_answerer_and_resume_generator(gpt_answerer, resume_generator_manager)
        bot.set_parameters(parameters)
        bot.start_login()

        # 6. Start applying
        bot.start_apply()

        # 7. Finish
        run = db.session.get(Run, run_id)
        run.status = 'finished'
        run.end_time = datetime.utcnow()
        db.session.commit()

    def stop(self):
        self.stop_event.set()
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass