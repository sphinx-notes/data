"""
sphinxnotes.data.renderer
~~~~~~~~~~~~~~~~~~~~~~~~~

Rendering markup text to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import TYPE_CHECKING

from docutils import nodes
from docutils.parsers.rst.states import Struct
from docutils.utils import new_document
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

if TYPE_CHECKING:
    from docutils.nodes import Node, system_message

# Possible render host of :meth:`pending_node.render`.
type Host = ParseHost | TransformHost
# Host of source parse phase (Phase.Parsing, Phase.Parsed).
type ParseHost = SphinxDirective | SphinxRole
# Host of source parse phase (Phase.Parsing, Phase.Parsed).
type TransformHost = SphinxTransform


@dataclass
class HostWrapper:
    v: Host

    @property
    def doctree(self) -> nodes.document:
        if isinstance(self.v, SphinxDirective):
            return self.v.state.document
        elif isinstance(self.v, SphinxRole):
            return self.v.inliner.document
        elif isinstance(self.v, SphinxTransform):
            return self.v.document
        else:
            raise NotImplementedError

    @property
    def parent(self) -> nodes.Element | None:
        if isinstance(self.v, SphinxDirective):
            return self.v.state.parent
        elif isinstance(self.v, SphinxRole):
            return self.v.inliner.parent
        else:
            return None


@dataclass
class Renderer:
    host: Host

    def render(
        self, text: str, inline: bool = False
    ) -> tuple[list[Node], list[system_message]]:
        if inline:
            return self._render_inline(text)
        else:
            return self._render(text), []

    def _render(self, text: str) -> list[Node]:
        if isinstance(self.host, SphinxDirective):
            return self.host.parse_text_to_nodes(text)
        elif isinstance(self.host, SphinxTransform):
            # TODO: sphinx>9
            # https://github.com/missinglinkelectronics/sphinxcontrib-globalsubs/pull/9/files
            settings = self.host.document.settings
            # TODO: dont create parser for every time
            parser = self.host.app.registry.create_source_parser(self.host.app, 'rst')
            doc = new_document('<generated text>', settings=settings)
            parser.parse(text, doc)
            return doc.children
        else:
            assert False

    def _render_inline(self, text: str) -> tuple[list[Node], list[system_message]]:
        if isinstance(self.host, SphinxDirective):
            return self.host.parse_inline(text)
        if isinstance(self.host, SphinxRole):
            inliner = self.host.inliner
            memo = Struct(
                document=inliner.document,
                reporter=inliner.reporter,
                language=inliner.language,
            )

            return inliner.parse(text, self.host.lineno, memo, inliner.parent)
        elif isinstance(self.host, SphinxTransform):
            # Fallback to normal non-inline render then extract inline
            # elements by self.
            # FIXME: error seems be ignored?
            ns = self._render(text)
            if ns and isinstance(ns[0], nodes.paragraph):
                ns = ns[0].children
            return ns, []
        else:
            assert False
