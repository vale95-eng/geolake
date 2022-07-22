import os
import logging

from jinja2 import Environment, FileSystemLoader, Template
from jinja2 import exceptions as ex

import jinja_filter as jf


class Converter:

    _LOG = logging.getLogger("Converter")
    RESURCE_DIR = os.path.join(".", "resources")
    DEFAULT_LIST_DETAILS_TEMPLATE_FILE = "basic_product.json.jinja2"
    DEFAULT_PRODUCT_TEMPLATE_FILE = "basic_product.json.jinja2"
    ENVIRONMENT = None
    PRODUCT_TEMPLATE = None

    @classmethod
    def load_templates(
        cls,
        list_dataset_template_file: str = None,
        product_template_file: str = None,
    ):
        cls._LOG("Loading Jinja2 template...")
        if not template_file:
            prod_template_file = cls.DEFAULT_PRODUCT_PRODUCT_TEMPLATE_FILE
        if not list_dataset_template_file:
            list_template_file = cls.DEFAULT_LIST_DETAILS_TEMPLATE_FILE
        loader = FileSystemLoader(searchpath=cls.RESURCE_DIR)
        cls.ENVIRONMENT = Environment(loader=loader)
        try:
            cls.PRODUCT_TEMPLATE = cls.ENVIRONMENT.get_template(
                prod_template_file
            )
            cls.PRODUCT_TEMPLATE = cls.ENVIRONMENT.get_template(
                list_template_file
            )
        except ex.TemplateNotFound as e:
            cls._LOG.error(
                "One of templates"
                f" `{os.path.join(cls.RESURCE_DIR, prod_template_file)}` or"
                f" `{os.path.join(cls.RESURCE_DIR, list_template_file)}` was"
                " not found"
            )
            raise e
        cls.load_filters()

    @classmethod
    def load_filters(cls):
        cls._LOG("Loading custom filters for Jinja2 environment...")
        cls.ENVIRONMENT.filters["required"] = jf.required
        cls.ENVIRONMENT.filters["escape_chars"] = jf.escape_chars

    @classmethod
    def render_list_datasets(cls):
        cls._LOG.debug("Rendering list of datasets for...")
        pass
        # TODO:

    @classmethod
    def render_details(cls, details: dict) -> str:
        cls._LOG.debug(f"Rendering details for `{dataset_id}`...")
        # TODO:
        args = cls.construct_dict(details)
        return cls.TEMPLATE.render(args)


class Widget:
    def __init__(
        self,
        wname,
        wlabel,
        wrequired,
        wparameter,
        wtype,
        wdetails=None,
        whelp=None,
        winfo=None,
    ):
        self.__data = {
            "name": str(wname),
            "label": str(wlabel),
            "required": bool(wrequired),
            "parameter": str(wparameter) if wparameter is not None else None,
            "type": str(wtype),
            "details": wdetails,
            "help": whelp,
            "info": winfo,
        }

    def __getitem__(self, key):
        return self.__data[key]

    def to_dict(self):
        return self.__data.copy()

    @classmethod
    def from_dict(cls, data):
        return Widget(**data)
