from __future__ import annotations
from dataclasses import dataclass
from pprint import pformat
from typing import Any, Callable
from enum import Enum

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.application import Sphinx
from sphinx.builders import Builder

from jinja2.sandbox import SandboxedEnvironment

from .data import Data
from .utils import Reporter

logger = logging.getLogger(__name__)

type MarkupParser = Callable[[str], list[nodes.Node]]


class Phase(Enum):
    Parsing = 'parsing'
    Parsed = 'parsed'
    Resolving = 'resolving'

    @classmethod
    def default(cls) -> Phase:
        return cls.Parsing

    @classmethod
    def option_spec(cls, arg):
        choice = directives.choice(arg, [x.value for x in cls])
        return cls[choice.title()]


@dataclass
class Template(object):
    text: str
    phase: Phase
    debug: bool

    def render(
        self, parser: MarkupParser, data: Data, extractx: dict[str, Any]
    ) -> list[nodes.Node]:
        ctx = data.ascontext()
        ctx.update(**extractx)
        text = self._render(ctx)

        ns = parser(text)

        if self.debug:
            reporter = Reporter('Template debug report')
            reporter.append_text('Data:')
            reporter.append_code(pformat(data), lang='python')
            reporter.append_text(
                f'Template (phase: {self.phase}, debug: {self.debug}):'
            )
            reporter.append_code(self.text, lang='jinja')
            reporter.append_text('Rendered ndoes:')
            reporter.append_code('\n'.join(n.pformat() for n in ns), lang='xml')

            ns.append(reporter)

        return ns

    def _render(self, ctx: dict[str, Any]) -> str:
        return _JinjaEnv().from_string(self.text).render(ctx)


class _JinjaEnv(SandboxedEnvironment):
    _builder: Builder
    # List of user defined filter factories.
    _filter_factories = {}

    @classmethod
    def setup(cls, app: Sphinx):
        """You must call this method before instantiating"""
        app.connect('builder-inited', cls._on_builder_inited)
        app.connect('build-finished', cls._on_build_finished)

    @classmethod
    def _on_builder_inited(cls, app: Sphinx):
        cls._builder = app.builder

    @classmethod
    def add_filter(cls, name: str, ff):
        cls._filter_factories[name] = ff

    @classmethod
    def _on_build_finished(cls, app: Sphinx, exception): ...

    def is_safe_attribute(self, obj, attr, value=None):
        """
        The sandboxed environment will call this method to check if the
        attribute of an object is safe to access. Per default all attributes
        starting with an underscore are considered private as well as the
        special attributes of internal python objects as returned by the
        is_internal_attribute() function.
        """
        if attr.startswith('_'):
            return False
        return super().is_safe_attribute(obj, attr, value)

    def __init__(self):
        super().__init__(
            extensions=[
                'jinja2.ext.loopcontrols',  # enable {% break %}, {% continue %}
            ]
        )
        logger.warning
        for name, factory in self._filter_factories.items():
            self.filters[name] = factory(self._builder.env)


def setup(app: Sphinx):
    _JinjaEnv.setup(app)
