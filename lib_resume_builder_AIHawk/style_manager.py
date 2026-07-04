from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Tuple

from src.logging import logger


class StyleManager:
    def __init__(self):
        self.styles_directory = Path(__file__).resolve().parent / "resume_style"

    def set_styles_directory(self, styles_directory: Path):
        self.styles_directory = styles_directory

    def get_styles(self) -> Dict[str, Tuple[str, str]]:
        styles_to_files: Dict[str, Tuple[str, str]] = {}
        try:
            if not self.styles_directory.exists():
                return styles_to_files
            for file_name in os.listdir(self.styles_directory):
                file_path = self.styles_directory / Path(file_name)
                if file_path.is_file():
                    with open(file_path, "r", encoding="utf-8") as file:
                        first_line = file.readline().strip()
                        if first_line.startswith("/*") and first_line.endswith("*/") and "$" in first_line:
                            content = first_line[2:-2].strip()
                            style_name, author_link = content.split("$", 1)
                            styles_to_files[style_name.strip()] = (file_name, author_link.strip())
        except PermissionError:
            logger.warning(f"Permission denied to access {self.styles_directory}.")
        return styles_to_files

    def format_choices(self, styles_to_files: Dict[str, Tuple[str, str]]) -> List[str]:
        return [f"{style_name} (style author -> {author_link})" for style_name, (file_name, author_link) in styles_to_files.items()]

    def get_style_path(self, selected_style: str) -> Path:
        styles = self.get_styles()
        file_name, _ = styles[selected_style]
        return self.styles_directory / file_name
