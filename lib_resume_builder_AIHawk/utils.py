from __future__ import annotations

import os
import time
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager

from src.logging import logger
from src.utils.chrome_utils import chrome_browser_options


def create_driver_selenium():
    options = chrome_browser_options()
    service = ChromeService(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def HTML_to_PDF(file_path):
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"The specified file does not exist: {file_path}")

    html_uri = f"file:///{os.path.abspath(file_path).replace(os.sep, '/')}"
    driver = create_driver_selenium()

    try:
        driver.get(html_uri)
        time.sleep(1.5)
        pdf_base64 = driver.execute_cdp_cmd(
            "Page.printToPDF",
            {
                "printBackground": True,
                "landscape": False,
                "paperWidth": 8.27,
                "paperHeight": 11.69,
                "marginTop": 0.4,
                "marginBottom": 0.4,
                "marginLeft": 0.35,
                "marginRight": 0.35,
                "displayHeaderFooter": False,
                "preferCSSPageSize": True,
                "generateDocumentOutline": False,
                "generateTaggedPDF": False,
                "transferMode": "ReturnAsBase64",
            },
        )
        return pdf_base64["data"]
    except WebDriverException as exc:
        raise RuntimeError(f"WebDriver exception occurred: {exc}") from exc
    finally:
        driver.quit()
