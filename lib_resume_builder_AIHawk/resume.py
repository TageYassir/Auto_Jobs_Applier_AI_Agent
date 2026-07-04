from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from src.logging import logger


@dataclass
class Resume:
    personal_information: Any = None
    education_details: Any = None
    experience_details: Any = None
    projects: Any = None
    achievements: Any = None
    certifications: Any = None
    languages: Any = None
    interests: Any = None
    availability: Any = None
    salary_expectations: Any = None
    self_identification: Any = None
    legal_authorization: Any = None
    work_preferences: Any = None

    def __init__(self, yaml_str: str):
        try:
            data = yaml.safe_load(yaml_str) or {}
        except yaml.YAMLError as exc:
            raise ValueError("Error parsing YAML file.") from exc
        except Exception as exc:
            raise Exception(f"Unexpected error while parsing YAML: {exc}") from exc

        if not isinstance(data, dict):
            raise TypeError("YAML data must be a dictionary.")

        for key, value in data.items():
            setattr(self, key, self._convert(value))

        for field_name in self.__dataclass_fields__:
            if not hasattr(self, field_name):
                setattr(self, field_name, None)

    @staticmethod
    def _convert(value):
        if isinstance(value, dict):
            return SimpleNamespace(**{key: Resume._convert(item) for key, item in value.items()})
        if isinstance(value, list):
            return [Resume._convert(item) for item in value]
        return value

    @staticmethod
    def _namespace_to_dict(value):
        if isinstance(value, SimpleNamespace):
            return {key: Resume._namespace_to_dict(item) for key, item in vars(value).items()}
        if isinstance(value, list):
            return [Resume._namespace_to_dict(item) for item in value]
        return value

    def to_dict(self) -> dict:
        return {
            field_name: self._namespace_to_dict(getattr(self, field_name))
            for field_name in self.__dataclass_fields__
        }

    def __str__(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False, allow_unicode=True)
