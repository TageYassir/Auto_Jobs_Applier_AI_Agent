import json
import os
import random
import time
from itertools import product
from pathlib import Path
import traceback
import threading          # <-- added
import urllib.parse

from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By

from ai_hawk.linkedIn_easy_applier import AIHawkEasyApplier
from config import JOB_MAX_APPLICATIONS, JOB_MIN_APPLICATIONS, MINIMUM_WAIT_TIME_IN_SECONDS

from src.job import Job
from src.logging import logger
from src.regex_utils import generate_regex_patterns_for_blacklisting
import re
import utils.browser_utils as browser_utils
import utils.time_utils


class EnvironmentKeys:
    def __init__(self):
        logger.debug("Initializing EnvironmentKeys")
        self.skip_apply = self._read_env_key_bool("SKIP_APPLY")
        self.disable_description_filter = self._read_env_key_bool("DISABLE_DESCRIPTION_FILTER")
        logger.debug(f"EnvironmentKeys initialized: skip_apply={self.skip_apply}, disable_description_filter={self.disable_description_filter}")

    @staticmethod
    def _read_env_key(key: str) -> str:
        value = os.getenv(key, "")
        logger.debug(f"Read environment key {key}: {value}")
        return value

    @staticmethod
    def _read_env_key_bool(key: str) -> bool:
        value = os.getenv(key) == "True"
        logger.debug(f"Read environment key {key} as bool: {value}")
        return value


class AIHawkJobManager:
    def __init__(self, driver):
        logger.debug("Initializing AIHawkJobManager")
        self.driver = driver
        self.set_old_answers = set()
        self.easy_applier_component = None
        # ----- NEW attributes for control panel -----
        self.stop_event = threading.Event()
        self.log_func = None
        self.run_id = None
        logger.debug("AIHawkJobManager initialized successfully")

    def set_parameters(self, parameters):
        logger.debug("Setting parameters for AIHawkJobManager")
        self.company_blacklist = parameters.get('company_blacklist', []) or []
        self.title_blacklist = parameters.get('title_blacklist', []) or []
        self.location_blacklist = parameters.get('location_blacklist', []) or []
        self.positions = parameters.get('positions', [])
        self.locations = parameters.get('locations', [])
        self.apply_once_at_company = parameters.get('apply_once_at_company', False)
        self.base_search_url = self.get_base_search_url(parameters)
        self.seen_jobs = []

        self.min_applicants = JOB_MIN_APPLICATIONS
        self.max_applicants = JOB_MAX_APPLICATIONS

        self.title_blacklist_patterns = generate_regex_patterns_for_blacklisting(self.title_blacklist)
        self.company_blacklist_patterns = generate_regex_patterns_for_blacklisting(self.company_blacklist)
        self.location_blacklist_patterns = generate_regex_patterns_for_blacklisting(self.location_blacklist)

        resume_path = parameters.get('uploads', {}).get('resume', None)
        self.resume_path = Path(resume_path) if resume_path and Path(resume_path).exists() else None
        self.output_file_directory = Path(parameters['outputFileDirectory'])
        self.env_config = EnvironmentKeys()
        logger.debug("Parameters set successfully")

    def set_gpt_answerer(self, gpt_answerer):
        logger.debug("Setting GPT answerer")
        self.gpt_answerer = gpt_answerer

    def set_resume_generator_manager(self, resume_generator_manager):
        logger.debug("Setting resume generator manager")
        self.resume_generator_manager = resume_generator_manager

    # ----- NEW: logging callback setter -----
    def set_db_logger(self, log_func):
        self.log_func = log_func

    # ----- NEW: helper for DB logging -----
    def _log(self, job, status, reason=None):
        if self.log_func and self.run_id is not None:
            self.log_func(self.run_id, job, status, reason)

    # ----- NEW: interruptible sleep -----
    def _sleep_or_stop(self, total_seconds):
        """Sleep in steps, return False if stopped."""
        for _ in range(int(total_seconds * 2)):
            if self.stop_event.is_set():
                return False
            time.sleep(0.5)
        return True

    def start_collecting_data(self):
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_sleep = 0
        minimum_time = 60 * 5
        minimum_page_time = time.time() + minimum_time

        for position, location in searches:
            if self.stop_event.is_set():
                break
            location_url = "&location=" + location
            job_page_number = -1
            logger.info(f"Collecting data for {position} in {location}.", color="yellow")
            try:
                while True:
                    if self.stop_event.is_set():
                        break
                    page_sleep += 1
                    job_page_number += 1
                    logger.info(f"Going to job page {job_page_number}", color="yellow")
                    self.next_job_page(position, location_url, job_page_number)
                    utils.time_utils.medium_sleep()
                    logger.info("Starting the collecting process for this page", color="yellow")
                    self.read_jobs()
                    logger.info("Collecting data on this page has been completed!", color="yellow")

                    time_left = minimum_page_time - time.time()
                    if time_left > 0:
                        logger.info(f"Sleeping for {time_left} seconds.")
                        if not self._sleep_or_stop(time_left):
                            break
                        minimum_page_time = time.time() + minimum_time
                    if page_sleep % 5 == 0:
                        sleep_time = random.randint(1, 5)
                        logger.info(f"Sleeping for {sleep_time / 60} minutes.")
                        if not self._sleep_or_stop(sleep_time):
                            break
                        page_sleep += 1
            except Exception:
                pass
            time_left = minimum_page_time - time.time()
            if time_left > 0:
                logger.info(f"Sleeping for {time_left} seconds.")
                if not self._sleep_or_stop(time_left):
                    break
                minimum_page_time = time.time() + minimum_time
            if page_sleep % 5 == 0:
                sleep_time = random.randint(50, 90)
                logger.info(f"Sleeping for {sleep_time / 60} minutes.")
                if not self._sleep_or_stop(sleep_time):
                    break
                page_sleep += 1

    def start_applying(self):
        logger.debug("Starting job application process")
        self.easy_applier_component = AIHawkEasyApplier(self.driver, self.resume_path, self.set_old_answers,
                                                          self.gpt_answerer, self.resume_generator_manager)
        searches = list(product(self.positions, self.locations))
        random.shuffle(searches)
        page_sleep = 0
        minimum_time = MINIMUM_WAIT_TIME_IN_SECONDS
        minimum_page_time = time.time() + minimum_time

        for position, location in searches:
            if self.stop_event.is_set():
                logger.info("Stop signal received, exiting.")
                break
            location_url = "&location=" + location
            job_page_number = -1
            logger.debug(f"Starting the search for {position} in {location}.")

            try:
                while True:
                    if self.stop_event.is_set():
                        break
                    page_sleep += 1
                    job_page_number += 1
                    logger.debug(f"Going to job page {job_page_number}")
                    self.next_job_page(position, location_url, job_page_number)
                    utils.time_utils.medium_sleep()
                    logger.debug("Starting the application process for this page...")

                    try:
                        jobs = self.get_jobs_from_page(scroll=True)
                        if not jobs:
                            logger.debug("No more jobs found on this page. Exiting loop.")
                            break
                    except Exception as e:
                        logger.error(f"Failed to retrieve jobs: {e}")
                        break

                    try:
                        self.apply_jobs()
                    except Exception as e:
                        logger.error(f"Error during job application: {e} {traceback.format_exc()}")
                        continue

                    logger.debug("Applying to jobs on this page has been completed!")

                    time_left = minimum_page_time - time.time()
                    # ----- REPLACED inputimeout -----
                    if time_left > 0:
                        logger.info(f"Sleeping for {time_left} seconds (auto mode).")
                        if not self._sleep_or_stop(time_left):
                            break
                    minimum_page_time = time.time() + minimum_time

                    if page_sleep % 5 == 0:
                        sleep_time = random.randint(5, 34)
                        logger.info(f"Sleeping for {sleep_time} seconds.")
                        if not self._sleep_or_stop(sleep_time):
                            break
                        page_sleep += 1
            except Exception as e:
                logger.error(f"Unexpected error during job search: {e}")
                continue

            time_left = minimum_page_time - time.time()
            if time_left > 0:
                logger.info(f"Sleeping for {time_left} seconds.")
                if not self._sleep_or_stop(time_left):
                    break
            minimum_page_time = time.time() + minimum_time

            if page_sleep % 5 == 0:
                sleep_time = random.randint(50, 90)
                logger.info(f"Sleeping for {sleep_time} seconds.")
                if not self._sleep_or_stop(sleep_time):
                    break
                page_sleep += 1

    def get_jobs_from_page(self, scroll=False):
        try:
            no_jobs_element = self.driver.find_element(By.CLASS_NAME, 'jobs-search-two-pane__no-results-banner--expand')
            if 'No matching jobs found' in no_jobs_element.text or 'unfortunately, things aren' in self.driver.page_source.lower():
                logger.debug("No matching jobs found on this page, skipping.")
                return []
        except NoSuchElementException:
            pass

        try:
            jobs_xpath_query = "//ul[contains(@class, 'scaffold-layout__list-container')]"
            jobs_container = self.driver.find_element(By.XPATH, jobs_xpath_query)

            if scroll:
                jobs_container_scrolableElement = jobs_container.find_element(By.XPATH,"..")
                logger.warning(f'is scrollable: {browser_utils.is_scrollable(jobs_container_scrolableElement)}')
                browser_utils.scroll_slow(self.driver, jobs_container_scrolableElement)
                browser_utils.scroll_slow(self.driver, jobs_container_scrolableElement, step=300, reverse=True)

            job_element_list = jobs_container.find_elements(By.XPATH, ".//li[contains(@class, 'jobs-search-results__list-item') and contains(@class, 'ember-view')]")

            if not job_element_list:
                logger.debug("No job class elements found on page, skipping.")
                return []

            return job_element_list

        except NoSuchElementException as e:
            logger.warning(f'No job results found on the page. \n exception: {traceback.format_exc()}')
            return []
        except Exception as e:
            logger.error(f"Error while fetching job elements: {e} {traceback.format_exc()}")
            return []

    def read_jobs(self):
        job_element_list = self.get_jobs_from_page()
        job_list = [self.job_tile_to_job(job_element) for job_element in job_element_list]
        for job in job_list:
            if self.is_blacklisted(job.title, job.company, job.link, job.location):
                logger.info(f"Blacklisted {job.title} at {job.company} in {job.location}, skipping...")
                self.write_to_file(job, "skipped")
                self._log(job, 'skipped', 'Blacklisted')
                continue
            try:
                self.write_to_file(job, 'data')
            except Exception as e:
                self.write_to_file(job, "failed")
                self._log(job, 'failed', str(e))
                continue

    def apply_jobs(self):
        job_element_list = self.get_jobs_from_page()
        job_list = [self.job_tile_to_job(job_element) for job_element in job_element_list]

        for job in job_list:
            logger.debug(f"Starting applicant for job: {job.title} at {job.company}")

            if self.is_previously_failed_to_apply(job.link):
                logger.debug(f"Previously failed to apply for {job.title} at {job.company}, skipping...")
                self._log(job, 'skipped', 'Previously failed')
                continue
            if self.is_blacklisted(job.title, job.company, job.link, job.location):
                logger.debug(f"Job blacklisted: {job.title} at {job.company} in {job.location}")
                self.write_to_file(job, "skipped", "Job blacklisted")
                self._log(job, 'skipped', 'Blacklisted')
                continue
            if self.is_already_applied_to_job(job.title, job.company, job.link):
                self.write_to_file(job, "skipped", "Already applied to this job")
                self._log(job, 'skipped', 'Already applied')
                continue
            if self.is_already_applied_to_company(job.company):
                self.write_to_file(job, "skipped", "Already applied to this company")
                self._log(job, 'skipped', 'Already applied to company')
                continue
            try:
                if job.apply_method not in {"Continue", "Applied", "Apply"}:
                    self.easy_applier_component.job_apply(job)
                    self.write_to_file(job, "success")
                    self._log(job, 'success')       # <-- added
                    logger.debug(f"Applied to job: {job.title} at {job.company}")
            except Exception as e:
                logger.error(f"Failed to apply for {job.title} at {job.company}: {e}", exc_info=True)
                self.write_to_file(job, "failed", f"Application error: {str(e)}")
                self._log(job, 'failed', str(e))    # <-- added
                continue

    def write_to_file(self, job: Job, file_name, reason=None):
        logger.debug(f"Writing job application result to file: {file_name}")
        pdf_path = Path(job.resume_path).resolve() if job.resume_path else Path("")
        pdf_path = pdf_path.as_uri() if pdf_path != Path("") else ""
        data = {
            "company": job.company,
            "job_title": job.title,
            "link": job.link,
            "job_recruiter": job.recruiter_link,
            "job_location": job.location,
            "pdf_path": pdf_path
        }
        if reason:
            data["reason"] = reason

        file_path = self.output_file_directory / f"{file_name}.json"
        if not file_path.exists():
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump([data], f, indent=4)
                logger.debug(f"Job data written to new file: {file_name}")
        else:
            with open(file_path, 'r+', encoding='utf-8') as f:
                try:
                    existing_data = json.load(f)
                except json.JSONDecodeError:
                    logger.error(f"JSON decode error in file: {file_path}")
                    existing_data = []
                existing_data.append(data)
                f.seek(0)
                json.dump(existing_data, f, indent=4)
                f.truncate()
                logger.debug(f"Job data appended to existing file: {file_name}")

    def get_base_search_url(self, parameters):
        logger.debug("Constructing base search URL")
        url_parts = []
        working_type_filter = []
        if parameters.get("onsite") == True:
            working_type_filter.append("1")
        if parameters.get("remote") == True:
            working_type_filter.append("2")
        if parameters.get("hybrid") == True:
            working_type_filter.append("3")

        if working_type_filter:
            url_parts.append(f"f_WT={'%2C'.join(working_type_filter)}")

        experience_levels = [str(i + 1) for i, (level, v) in enumerate(parameters.get('experience_level', {}).items()) if v]
        if experience_levels:
            url_parts.append(f"f_E={','.join(experience_levels)}")
        url_parts.append(f"distance={parameters['distance']}")
        job_types = [key[0].upper() for key, value in parameters.get('job_types', {}).items() if value]
        if job_types:
            url_parts.append(f"f_JT={','.join(job_types)}")
        date_mapping = {
            "all_time": "",
            "month": "&f_TPR=r2592000",
            "week": "&f_TPR=r604800",
            "24_hours": "&f_TPR=r86400"
        }
        date_param = next((v for k, v in date_mapping.items() if parameters.get('date', {}).get(k)), "")
        url_parts.append("f_LF=f_AL")  # Easy Apply
        base_url = "&".join(url_parts)
        full_url = f"?{base_url}{date_param}"
        logger.debug(f"Base search URL constructed: {full_url}")
        return full_url

    def next_job_page(self, position, location, job_page):
        logger.debug(f"Navigating to next job page: {position} in {location}, page {job_page}")
        encoded_position = urllib.parse.quote(position)
        self.driver.get(
            f"https://www.linkedin.com/jobs/search/{self.base_search_url}&keywords={encoded_position}{location}&start={job_page * 25}")

    def job_tile_to_job(self, job_tile) -> Job:
        logger.debug("Extracting job information from tile")
        job = Job()

        try:
            job.title = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').find_element(By.TAG_NAME, 'strong').text
            logger.debug(f"Job title extracted: {job.title}")
        except NoSuchElementException:
            logger.warning("Job title is missing.")

        try:
            job.link = job_tile.find_element(By.CLASS_NAME, 'job-card-list__title').get_attribute('href').split('?')[0]
            logger.debug(f"Job link extracted: {job.link}")
        except NoSuchElementException:
            logger.warning("Job link is missing.")

        try:
            job.company = job_tile.find_element(By.XPATH, ".//div[contains(@class, 'artdeco-entity-lockup__subtitle')]//span").text
            logger.debug(f"Job company extracted: {job.company}")
        except NoSuchElementException as e:
            logger.warning(f'Job company is missing. {e} {traceback.format_exc()}')

        try:
            match = re.search(r'/jobs/view/(\d+)/', job.link)
            if match:
                job.id = match.group(1)
            else:
                logger.warning(f"Job ID not found in link: {job.link}")
            logger.debug(f"Job ID extracted: {job.id} from url:{job.link}") if match else logger.warning(f"Job ID not found in link: {job.link}")
        except Exception as e:
            logger.warning(f"Failed to extract job ID: {e}", exc_info=True)

        try:
            job.location = job_tile.find_element(By.CLASS_NAME, 'job-card-container__metadata-item').text
        except NoSuchElementException:
            logger.warning("Job location is missing.")

        try:
            job_state = job_tile.find_element(By.XPATH, ".//ul[contains(@class, 'job-card-list__footer-wrapper')]//li[contains(@class, 'job-card-container__apply-method')]").text
        except NoSuchElementException as e:
            try:
                job_state = job_tile.find_element(By.XPATH, ".//ul[contains(@class, 'job-card-list__footer-wrapper')]//li[contains(@class, 'job-card-container__footer-job-state')]").text
                job.apply_method = "Applied"
                logger.warning(f'Apply method not found, state {job_state}. {e} {traceback.format_exc()}')
            except NoSuchElementException as e:
                logger.warning(f'Apply method and state not found. {e} {traceback.format_exc()}')

        return job

    def is_blacklisted(self, job_title, company, link, job_location):
        logger.debug(f"Checking if job is blacklisted: {job_title} at {company} in {job_location}")
        title_blacklisted = any(re.search(pattern, job_title, re.IGNORECASE) for pattern in self.title_blacklist_patterns)
        company_blacklisted = any(re.search(pattern, company, re.IGNORECASE) for pattern in self.company_blacklist_patterns)
        location_blacklisted = any(re.search(pattern, job_location, re.IGNORECASE) for pattern in self.location_blacklist_patterns)
        link_seen = link in self.seen_jobs
        is_blacklisted = title_blacklisted or company_blacklisted or location_blacklisted or link_seen
        logger.debug(f"Job blacklisted status: {is_blacklisted}")
        return is_blacklisted

    def is_already_applied_to_job(self, job_title, company, link):
        link_seen = link in self.seen_jobs
        if link_seen:
            logger.debug(f"Already applied to job: {job_title} at {company}, skipping...")
        return link_seen

    def is_already_applied_to_company(self, company):
        if not self.apply_once_at_company:
            return False
        output_files = ["success.json"]
        for file_name in output_files:
            file_path = self.output_file_directory / file_name
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    try:
                        existing_data = json.load(f)
                        for applied_job in existing_data:
                            if applied_job['company'].strip().lower() == company.strip().lower():
                                logger.debug(f"Already applied at {company} (once per company policy), skipping...")
                                return True
                    except json.JSONDecodeError:
                        continue
        return False

    def is_previously_failed_to_apply(self, link):
        file_name = "failed"
        file_path = self.output_file_directory / f"{file_name}.json"
        if not file_path.exists():
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([], f)

        with open(file_path, 'r', encoding='utf-8') as f:
            try:
                existing_data = json.load(f)
            except json.JSONDecodeError:
                logger.error(f"JSON decode error in file: {file_path}")
                return False
            for data in existing_data:
                data_link = data['link']
                if data_link == link:
                    return True
        return False