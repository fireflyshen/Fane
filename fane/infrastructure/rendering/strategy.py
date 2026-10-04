from abc import ABC, abstractmethod

from jinja2 import Template

from fane.core.models import Order


class TemplateStrategy(ABC):
    expense_list: list[str]
    income_list: list[str]

    @abstractmethod
    def template_parser(self, order: Order) -> None:
        pass

    @classmethod
    @abstractmethod
    def get_template_content(cls, template_name: str) -> Template:
        pass
