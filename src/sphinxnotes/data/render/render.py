from __future__ import annotations
from dataclasses import dataclass
from enum import Enum

from docutils import nodes
from sphinx.transforms import SphinxTransform
from sphinx.util.docutils import SphinxDirective, SphinxRole


class Phase(Enum):
    Parsing = 'parsing'
    Parsed = 'parsed'
    PostTranform = 'post-transform'
    # TODO: transform?

    @classmethod
    def default(cls) -> Phase:
        return cls.Parsing


@dataclass
class Template:
    #: Jinja template for rendering the context.
    text: str
    #: The render phase.
    phase: Phase = Phase.default()
    #: Enable debug output (shown as :cls:`nodes.system_message` in document.)
    debug: bool = False


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
