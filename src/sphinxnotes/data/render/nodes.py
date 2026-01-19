from __future__ import annotations
from enum import Enum
from typing import Any

from docutils import nodes

from ..data import PendingData, ParsedData
from ..utils import Unpicklable


class Phase(Enum):
    Parsing = 'parsing'
    Parsed = 'parsed'
    PostTranform = 'post-transform'
    # TODO: transform?

    @classmethod
    def default(cls) -> Phase:
        return cls.Parsing


class Base(nodes.Element): ...


class pending_data(Base, Unpicklable):
    # The data to be rendered by Jinja template.
    data: PendingData | ParsedData | dict[str, Any]
    # The extra context for Jina template.
    extra: dict[str, Any]
    #: Jinja template for rendering the context.
    template: str
    #: Whether rendering to inline nodes.
    inline: bool = False
    #: The render phase.
    phase: Phase
    #: Enable debug output (shown as :cls:`nodes.system_message` in document.)
    debug: bool

    def __init__(
        self,
        data: PendingData | ParsedData | dict[str, Any],
        tmpl: str,
        phase: Phase = Phase.default(),
        debug: bool = True,
        rawsource='',
        *children,
        **attributes,
    ) -> None:
        super().__init__(rawsource, *children, **attributes)
        self.data = data
        self.extra = {}
        self.template = tmpl
        self.phase = phase
        self.debug = debug


class rendered_data(Base, nodes.container):
    # The data used when rendering this node.
    data: ParsedData | dict[str, Any] | None
