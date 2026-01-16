from __future__ import annotations
from dataclasses import dataclass, field as dataclass_field
from os import wait
from pprint import pformat
from typing import TYPE_CHECKING
from enum import Enum

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, DebugUndefined

from .data import Data
from .utils import Reporter

if TYPE_CHECKING:
    from typing import Any, Callable
    from sphinx.builders import Builder
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)

type MarkupParser = Callable[[str], list[nodes.Node]]

class Phase(Enum):
    Parsing = 'parsing'
    Parsed = 'parsed'
    PostTranform = 'post-transform'
    # TODO: transform?

    @classmethod
    def default(cls) -> Phase:
        return cls.Parsing

    @classmethod
    def option_spec(cls, arg):
        choice = directives.choice(arg, [x.value for x in cls])
        return cls[choice.title()]


type Context = Data | dict[str, Any]
type ExtraContext = dict[str, Any]


@dataclass
class Template(object):
    text: str
    phase: Phase
    debug: bool

    def render(self, parser: MarkupParser, ctx: dict[str, Any],
               extra: dict[str, Any] = {}) -> list[nodes.Node]:
        finalctx = self._merge_ctx(ctx)
        text = self._render(finalctx)
        ns = parser(text)

        if self.debug:
            reporter = Reporter('Template debug report')

            reporter.text('Main context:')
            reporter.code(pformat(ctx.main), lang='python')

            reporter.text('Extra context keys:')
            reporter.code(pformat(ctx.extra.keys()), lang='python')

            reporter.text(f'Template (phase: {self.phase}, debug: {self.debug}):')
            reporter.code(self.text, lang='jinja')

            reporter.text('Rendered ndoes:')
            reporter.code('\n'.join(n.pformat() for n in ns), lang='xml')

            ns.append(reporter)

        return ns


    def _merge_ctx(self, ctx: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
        if isinstance(ctx.main, Data):
            finalctx = ctx.main.asdict()
        elif isinstance(ctx, dict):
            finalctx = ctx.main.copy()
        else:
            assert False

        for name, ectx in ctx.extra.items():
            if name in finalctx:
                continue
            finalctx[name] = ectx

        return finalctx


    def _render(self, ctx: dict[str, Any]) -> str:
        extensions = [
            'jinja2.ext.loopcontrols',  # enable {% break %}, {% continue %}
        ]
        if self.debug:
            extensions.append('jinja2.ext.debug')

        env = _JinjaEnv(
            undefined=DebugUndefined if self.debug else StrictUndefined,
            extensions=extensions,
        )
        # TODO: cache jinja env

        return env.from_string(self.text).render(ctx)


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, factory in self._filter_factories.items():
            self.filters[name] = factory(self._builder.env)


def setup(app: Sphinx):
    _JinjaEnv.setup(app)
