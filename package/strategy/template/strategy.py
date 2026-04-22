from abc import abstractmethod, ABC

from ir.ir import Order


class TemplateStrategy(ABC):

    expense_list: list[str]
    income_list: list[str]

    @classmethod
    @abstractmethod
    def template_parser(self, order: Order):
        pass

    @abstractmethod
    def get_template_content(self, template_name: str):
        pass
