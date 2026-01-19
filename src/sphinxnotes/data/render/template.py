from __future__ import annotations
from dataclasses import dataclass
from pprint import pformat
from typing import TYPE_CHECKING

from jinja2.sandbox import SandboxedEnvironment
from jinja2 import StrictUndefined, DebugUndefined

from ..data import ParsedData
from ..utils import Report

if TYPE_CHECKING:
    from typing import Any
    from sphinx.builders import Builder
    from sphinx.application import Sphinx


@dataclass
class Template:
    text: str

    def render(
        self,
        data: ParsedData | dict[str, Any],
        extra: dict[str, Any] = {},
        debug: Report | None = None,
    ) -> str:
        if debug:
            debug.text('Starting Jinja template rendering...')

            debug.text('Data:')
            debug.code(pformat(data), lang='python')
            debug.text('Extra context (just key):')
            debug.code(pformat(list(extra.keys())), lang='python')

        # Convert data to context dict.
        if isinstance(data, ParsedData):
            ctx = data.asdict()
        elif isinstance(data, dict):
            ctx = data.copy()

        # Merge extra context and main context.
        conflicts = set()
        for name, e in extra.items():
            if name not in ctx:
                ctx[name] = e
            else:
                conflicts.add(name)

        text = self._render(ctx, debug=debug is not None)

        return text

    def _render(self, ctx: dict[str, Any], debug: bool = False) -> str:
        extensions = [
            'jinja2.ext.loopcontrols',  # enable {% break %}, {% continue %}
        ]
        if debug:
            extensions.append('jinja2.ext.debug')

        env = _JinjaEnv(
            undefined=DebugUndefined if debug else StrictUndefined,
            extensions=extensions,
        )
        # TODO: cache jinja env

        return env.from_string(self.text).render(ctx)

    def _report_self(self, reporter: Report) -> None:
        reporter.text('Template:')
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
