from __future__ import annotations
from typing import TYPE_CHECKING, override
from dataclasses import dataclass

from docutils import nodes
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import find_current_section
from .utils.ctxproxy import proxy
from .renderer import Host, ParseHost
from .render import (
    EXTRACTX_REGISTRY,
    ParsePhaseContextGenerator,
    RenderPhaseContextGenerator,
)

if TYPE_CHECKING:
    from typing import Any

@dataclass
class _Host:
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


class MarkupContextGenerator(ParsePhaseContextGenerator):
    @override
    def generate(self, caller: ParseHost) -> Any:
        isdir = isinstance(caller, SphinxDirective)
        return {
            'type': 'directive' if isdir else 'role',
            'name': caller.name,
            'lineno': caller.lineno,
            'rawtext': caller.block_text if isdir else caller.rawtext,
        }


class DocContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Host) -> Any:
        return proxy(_Host(caller).doctree)


class SectionContextGenerator(ParsePhaseContextGenerator):
    @override
    def generate(self, caller: ParseHost) -> Any:
        parent = _Host(caller).parent
        return proxy(find_current_section(parent))


class SphinxEnvContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Host) -> Any:
        return proxy(caller.env)


class SphinxConfigContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Host) -> Any:
        return proxy(caller.config)


EXTRACTX_REGISTRY.add_parsing('markup', MarkupContextGenerator())
EXTRACTX_REGISTRY.add_parsing('section', SectionContextGenerator())
EXTRACTX_REGISTRY.add_render('doc', DocContextGenerator())
EXTRACTX_REGISTRY.add_render('env', SphinxEnvContextGenerator())
EXTRACTX_REGISTRY.add_render('config', SphinxConfigContextGenerator())
