"""
sphinxnotes.data.render
~~~~~~~~~~~~~~~~~~~~~~~

Rendering markup text to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Callable

from docutils import nodes
from docutils.parsers.rst.states import Struct
from docutils.utils import new_document
from docutils.nodes import Node, system_message
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import Reporter

if TYPE_CHECKING:
    ...

logger = logging.getLogger(__name__)


class Renderer:
    v: SphinxDirective | SphinxRole | SphinxTransform

    def __init__(self, v: SphinxDirective | SphinxRole | SphinxTransform) -> None:
        self.v = v

    def render(
        self, text: str, inline: bool = False
    ) -> tuple[list[Node], list[Reporter]]:
        if inline:
            return self._render(text)
        else:
            return self._render_inline(text)

    def _render(self, text: str) -> tuple[list[Node], list[Reporter]]:
        v = self.v
        if isinstance(v, SphinxDirective):
            return self._safe_render(v.parse_text_to_nodes, text)
        elif isinstance(v, SphinxTransform):
            # TODO: sphinx>9
            # https://github.com/missinglinkelectronics/sphinxcontrib-globalsubs/pull/9/files
            settings = v.document.settings
            # TODO: dont create parser for every time
            parser = v.app.registry.create_source_parser(v.app, 'rst')

            def parse(text):
                doc = new_document('<generated text>', settings=settings)
                parser.parse(text, doc)
                return doc.children

            return self._safe_render(parse, text)
        else:
            assert False

    def _render_inline(self, text: str) -> tuple[list[Node], list[Reporter]]:
        v = self.v
        if isinstance(v, SphinxDirective):
            return self._safe_render_inline(v.parse_inline, text)
        if isinstance(v, SphinxRole):
            memo = Struct(
                document=v.inliner.document,
                reporter=v.inliner.reporter,
                language=v.inliner.language,
            )

            def role_parse(text):
                return v.inliner.parse(text, v.lineno, memo, v.inliner.parent)

            return self._safe_render_inline(role_parse, text)
        elif isinstance(v, SphinxTransform):
            # Fallback to normal non-inline render then extract inline
            # elements by self.
            ns, rs = self._render(text)
            if ns and isinstance(ns[0], nodes.paragraph):
                ns = ns[0].children
            return ns, rs
        else:
            assert False

    def _safe_render(
        self, fn: Callable[[str], list[Node]], text: str
    ) -> tuple[list[Node], list[Reporter]]:
        try:
            ns = fn(text)
        except Exception:
            reporter = Reporter('Failed to render the follwing text to nodes', 'ERROR')
            reporter.code(text)
            return [], [reporter]
        return ns, []

    def _safe_render_inline(
        self, fn: Callable[[str], tuple[list[Node], list[system_message]]], text: str
    ) -> tuple[list[Node], list[Reporter]]:
        try:
            ns, msgs = fn(text)
        except Exception:
            reporter = Reporter(
                'Failed to render the follwing text to inline nodes', 'ERROR'
            )
            reporter.code(text)
            return [], [reporter]

        # Convert system_message to Reporter.
        rs = []
        for msg in msgs:
            r = Reporter('Parser generated message:', 'WARNING')
            r += msg.children
            rs.append(r)

        return ns, rs
