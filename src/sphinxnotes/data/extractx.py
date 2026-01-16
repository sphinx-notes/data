from __future__ import annotations
from typing import override

from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import find_current_section
from .utils.ctxproxy import proxy
from .render import (
    EXTRACTX_REGISTRY,
    ParsePhaseContextGenerator,
    FullPhaseContextGenerator,
    ParseCaller,
    Caller,
    pending_node,
)
from .template import Context


class MarkupContextGenerator(ParsePhaseContextGenerator):
    @override
    def generate(self, caller: ParseCaller, n: pending_node) -> Context:
        isdir = isinstance(caller, SphinxDirective)
        return {
            'type': 'directive' if isdir else 'role',
            'name': caller.name,
            'lineno': caller.lineno,
            'rawtext': caller.block_text if isdir else caller.rawtext,
        }


class DocContextGenerator(FullPhaseContextGenerator):
    @override
    def generate(self, caller: Caller, n: pending_node) -> Context:
        if isinstance(caller, SphinxDirective):
            return proxy(caller.state.document)
        elif isinstance(caller, SphinxRole):
            return proxy(caller.inliner.document)
        elif isinstance(caller, SphinxTransform):
            return proxy(caller.document)
        else:
            assert False


class SectionContextGenerator(FullPhaseContextGenerator):
    @override
    def generate(self, caller: Caller, n: pending_node) -> Context:
        if n.parent:
            return proxy(find_current_section(n.parent))
        elif isinstance(caller, SphinxDirective):
            return proxy(find_current_section(caller.state.parent))
        elif isinstance(caller, SphinxRole):
            return proxy(caller.inliner.parent)
        else:
            assert False


class SphinxEnvContextGenerator(FullPhaseContextGenerator):
    @override
    def generate(self, caller: Caller, n: pending_node) -> Context:
        return proxy(caller.env)


class SphinxConfigContextGenerator(FullPhaseContextGenerator):
    @override
    def generate(self, caller: Caller, n: pending_node) -> Context:
        return proxy(caller.config)


EXTRACTX_REGISTRY.add_parsing_phase_context('markup', MarkupContextGenerator())
EXTRACTX_REGISTRY.add_full_phase_context('doc', DocContextGenerator())
EXTRACTX_REGISTRY.add_full_phase_context('section', SectionContextGenerator())
EXTRACTX_REGISTRY.add_full_phase_context('env', SphinxEnvContextGenerator())
EXTRACTX_REGISTRY.add_full_phase_context('config', SphinxConfigContextGenerator())
