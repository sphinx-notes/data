"""
sphinxnotes.data.renderer
~~~~~~~~~~~~~~~~~~~~~~~~~

Rendering markup text to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from docutils import nodes
from docutils.parsers.rst.states import Struct
from docutils.utils import new_document
from docutils.nodes import Node, system_message
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import Report

if TYPE_CHECKING:
    from typing import Callable

logger = logging.getLogger(__name__)

# Possible render host of :meth:`pending_node.render`.
type Host = ParseHost | TransformHost
# Host of source parse phase (Phase.Parsing, Phase.Parsed).
type ParseHost = SphinxDirective | SphinxRole
# Host of source parse phase (Phase.Parsing, Phase.Parsed).
type TransformHost = SphinxTransform

class Renderer:
    host: SphinxDirective | SphinxRole | SphinxTransform

    def __init__(self, host: Host) -> None:
        self.host = host

    def render(self, text: str, inline: bool = False) -> list[Node]:
        if inline:
            return self._render_inline(text)
        else:
            return self._render(text)

    def _render(self, text: str) -> list[Node]:
        host = self.host
        if isinstance(host, SphinxDirective):
            return self._safe_render(host.parse_text_to_nodes, text)
        elif isinstance(host, SphinxTransform):
            # TODO: sphinx>9
            # https://github.com/missinglinkelectronics/sphinxcontrib-globalsubs/pull/9/files
            settings = host.document.settings
            # TODO: dont create parser for every time
            parser = host.app.registry.create_source_parser(host.app, 'rst')

            def parse(text):
                doc = new_document('<generated text>', settings=settings)
                parser.parse(text, doc)
                return doc.children

            return self._safe_render(parse, text)
        else:
            assert False

    def _render_inline(self, text: str) -> list[Node]:
        v = self.host
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
            # FIXME: error seems be ignored?
            ns = self._render(text)
            if ns and isinstance(ns[0], nodes.paragraph):
                ns = ns[0].children
            return ns
        else:
            assert False

    def _safe_render(self, fn: Callable[[str], list[Node]], text: str) -> list[Node]:
        try:
            ns = fn(text)
        except Exception:
            report = Report('Failed to render the follwing text to nodes', 'ERROR')
            report.code(text)
            return [report]
        return ns

    def _safe_render_inline(
        self, fn: Callable[[str], tuple[list[Node], list[system_message]]], text: str
    ) -> list[Node]:
        try:
            ns, msgs = fn(text)
        except Exception:
            report = Report(
                'Failed to render the follwing text to inline nodes', 'ERROR'
            )
            report.code(text)
            return [report]

        # Convert system_message to Reporter.
        for msg in msgs:
            r = Report('Parser generated message:', 'WARNING')
            r += msg.children
            ns.append(r)

        return ns
