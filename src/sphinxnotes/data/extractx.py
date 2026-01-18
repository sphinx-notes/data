from __future__ import annotations
from typing import TYPE_CHECKING, override

from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import find_current_section
from .utils.ctxproxy import proxy
from .render import (
    EXTRACTX_REGISTRY,
    ParsePhaseContextGenerator,
    RenderPhaseContextGenerator,
    ParseCaller,
    Caller,
)

if TYPE_CHECKING:
    from typing import Any


class MarkupContextGenerator(ParsePhaseContextGenerator):
    @override
    def generate(self, caller: ParseCaller) -> Any:
        isdir = isinstance(caller, SphinxDirective)
        return {
            'type': 'directive' if isdir else 'role',
            'name': caller.name,
            'lineno': caller.lineno,
            'rawtext': caller.block_text if isdir else caller.rawtext,
        }


class DocContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Caller) -> Any:
        if isinstance(caller, SphinxDirective):
            return proxy(caller.state.document)
        elif isinstance(caller, SphinxRole):
            return proxy(caller.inliner.document)
        elif isinstance(caller, SphinxTransform):
            return proxy(caller.document)
        else:
            assert False


class SectionContextGenerator(ParsePhaseContextGenerator):
    @override
    def generate(self, caller: ParseCaller) -> Any:
        if isinstance(caller, SphinxDirective):
            return proxy(find_current_section(caller.state.parent))
        elif isinstance(caller, SphinxRole):
            return proxy(caller.inliner.parent)
        else:
            assert False


class SphinxEnvContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Caller) -> Any:
        return proxy(caller.env)


class SphinxConfigContextGenerator(RenderPhaseContextGenerator):
    @override
    def generate(self, caller: Caller) -> Any:
        return proxy(caller.config)


EXTRACTX_REGISTRY.add_parsing('markup', MarkupContextGenerator())
EXTRACTX_REGISTRY.add_parsing('section', SectionContextGenerator())
EXTRACTX_REGISTRY.add_render('doc', DocContextGenerator())
EXTRACTX_REGISTRY.add_render('env', SphinxEnvContextGenerator())
EXTRACTX_REGISTRY.add_render('config', SphinxConfigContextGenerator())
