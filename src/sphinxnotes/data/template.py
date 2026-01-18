from __future__ import annotations
from dataclasses import dataclass
from pprint import pformat
from typing import TYPE_CHECKING
from enum import Enum

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, DebugUndefined

from .data import ParsedData
from .utils import Reporter
from .renderer import Renderer

if TYPE_CHECKING:
    from typing import Any
    from sphinx.builders import Builder
    from sphinx.application import Sphinx


logger = logging.getLogger(__name__)


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


@dataclass
class Template:
    text: str
    phase: Phase
    debug: bool

    def render(
        self,
        renderer: Renderer,
        data: ParsedData | dict[str, Any],
        extra: dict[str, Any] = {},
        inline: bool = False,
    ) -> tuple[list[nodes.Node], list[Reporter]]:
        # Main context to dic.
        if isinstance(data, ParsedData):
            ctx = data.asdict()
        elif isinstance(data, dict):
            ctx = data.copy()
        else:
            assert False

        # Merge extra context and main context.
        conflicts = set()
        for name, e in extra.items():
            if name not in ctx:
                ctx[name] = e
            else:
                conflicts.add(name)

        text, reporter = self._safe_render(ctx)
        if reporter and reporter.is_error():
            return [], [reporter]

        ns, rs = renderer.render(text, inline=inline)
        # FIXME: reporter is missing

        if self.debug:
            reporter = Reporter('Template debug report')

            reporter.text('Data:')
            reporter.code(pformat(data), lang='python')

            reporter.text('Extra (just key):')
            reporter.code(pformat(list(extra.keys())), lang='python')

            reporter.text('Conflict keys:')
            reporter.code(pformat(list(conflicts)), lang='python')

            self._report_self(reporter)

            reporter.text(f'Template (phase: {self.phase}, debug: {self.debug}):')
            reporter.code(self.text, lang='jinja')

            reporter.text('Rendered ndoes:')
            reporter.code('\n'.join(n.pformat() for n in ns), lang='xml')

            rs.append(reporter)

        return ns, rs

    def _safe_render(self, ctx: dict[str, Any]) -> tuple[str, Reporter | None]:
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

        try:
            text = env.from_string(self.text).render(ctx)
        except Exception:
            reporter = Reporter('Failed to render Jinja template:', 'ERROR')
            reporter.text('Context:')
            reporter.code(pformat(ctx), lang='python')
            self._report_self(reporter)
            reporter.excption()
            return '', reporter

        return text, None

    def _report_self(self, reporter: Reporter) -> None:
        reporter.text(f'Template (phase: {self.phase}, debug: {self.debug}):')
        reporter.code(self.text, lang='jinja')


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
