"""
sphinxnotes.data.render
~~~~~~~~~~~~~~~~~~~~~~~

Module for rendering data to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, override, final, cast, Callable
from abc import abstractmethod, ABC
from dataclasses import dataclass

from docutils import nodes
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform
from sphinx.transforms.post_transforms import SphinxPostTransform, ReferencesResolver

from .data import Schema, RawData, PendingData, ParsedData
from .template import Template, Phase
from .utils import (
    role_parse_text_to_nodes,
    parse_text_to_nodes,
    Unpicklable,
    Reporter,
)

if TYPE_CHECKING:
    from typing import Any
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment
    from sphinx.config import Config
    from .template import MarkupParser

logger = logging.getLogger(__name__)

# ========================
# Who is caller of render?
# ========================

# Possible caller of :meth:`pending_node.render` on source parse phase
# (parsing, parsed).
type ParseCaller = SphinxDirective | SphinxRole
# Possible caller of :meth:`pending_node.render` on transform phase.
type TransformCaller = SphinxTransform | SphinxPostTransform
# Possible caller of :meth:`pending_node.render`.
type Caller = ParseCaller | TransformCaller


@dataclass
class _Caller:
    v: Caller

    @property
    def env(self) -> BuildEnvironment:
        return self.v.env

    @property
    def config(self) -> Config:
        return self.v.config

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
    def markup_parser(self) -> MarkupParser:
        if isinstance(self.v, SphinxDirective):
            return self.v.parse_text_to_nodes
        elif isinstance(self.v, SphinxRole):

            def wrapper(text: str) -> list[nodes.Node]:
                return role_parse_text_to_nodes(self.v, text)

            return wrapper
        else:
            return parse_text_to_nodes

    @property
    def inline_markup_parser(self) -> MarkupParser:
        if isinstance(self.v, SphinxDirective):
            v = cast(SphinxDirective, self.v)

            def wrapper(text: str) -> list[nodes.Node]:
                ns, _ = v.parse_inline(text)
                return ns

            return wrapper
        elif isinstance(self.v, SphinxRole):

            def wrapper(text: str) -> list[nodes.Node]:
                return role_parse_text_to_nodes(self.v, text)

            return wrapper
        else:
            # TODO:
            return parse_text_to_nodes

    @property
    def parent(self) -> nodes.Element | None:
        if isinstance(self.v, SphinxDirective):
            return self.v.state.parent
        elif isinstance(self.v, SphinxRole):
            return self.v.inliner.parent
        else:
            return None

    def reporter(self, e: ValueError) -> Exception:
        if isinstance(self, SphinxDirective):
            raise self.error(str(e))
        elif isinstance(self, SphinxRole):
            ...  # TODO
        else:
            ...  # TODO


# ================
# Nodes definitons
# ================

# @dataclass
# class _PendingData(Data):
#     raw: RawData
#     schema: Schema
#
#     def parse(self) -> ParsedData:
#         return self.schema.parse(self.raw)
#
#     @override
#     def asdict(self) -> dict[str, Any]:
#         return self.parse().asdict()
#
#     def resolve_external(self, caller: _Caller, owner: pending_node) -> None:
#         if not self.raw.name and self.need_external_name:
#             if ns := self._resolve_external_name(caller, owner):
#                 self.raw.name = ns.astext()
#         if not self.raw.content and self.need_external_content:
#             if ns := self._resolve_external_content(caller, owner):
#                 self.raw.content = '\n\n'.join([x.astext() for x in ns])
#
#     def _resolve_external_name(self, caller: _Caller, owner: pending_node) -> nodes.Node | None:
#         # NOTE: the pending_data_node may be just created and haven't inserted
#         # to doctree (on Phase.Parsing).
#         return find_titular_node_upward(owner.parent or caller.parent)
#
#     def _resolve_external_content(self, caller: _Caller, owner: pending_node) -> list[nodes.Node]:
#         if not owner.parent:
#             return []  # TODO
#         contnodes = []
#         for i, child in enumerate(owner.parent):
#             if child == self:
#                 contnodes = owner.parent[i:]
#                 break
#         return contnodes
#


class BaseNode(nodes.Element): ...


class RenderedNode(BaseNode):
    # The data used when rendering this node.
    data: ParsedData | dict[str, Any]

    def __init__(
        self, data: ParsedData | dict[str, Any], rawsource='', *children, **attributes
    ) -> None:
        super().__init__(rawsource, *children, **attributes)
        self.data = data


class rendered_node(RenderedNode, nodes.container): ...


class rendered_inline_node(RenderedNode, nodes.inline): ...


class pending_node(BaseNode, nodes.Invisible, Unpicklable):
    # The data to be rendered.
    data: PendingData | ParsedData | dict[str, Any]
    # The extra context as a supplement to data.
    extra: _ExtraContextManager
    #: Template for rendering the context.
    template: Template
    #: Whether inline element.
    inline: bool = False
    #: Do not use :cls:`RenderedNode` as container of rendered nodes.
    seamless: bool = False

    def __init__(
        self,
        data: PendingData | ParsedData | dict[str, Any],
        tmpl: Template,
        rawsource='',
        *children,
        **attributes,
    ) -> None:
        super().__init__(rawsource, *children, **attributes)
        self.data = data
        self.extra = _ExtraContextManager()
        self.template = tmpl

    def render(self, caller: Caller, replace: bool = False) -> RenderedNode:
        # Generate and save full-phase extra contexts for later use.
        self.extra.on_rendering(caller)

        if isinstance(self.data, PendingData):
            data = self.data.parse()
        elif isinstance(self.data, ParsedData):
            data = self.data
        elif isinstance(self.data, dict):
            data = self.data
        else:
            assert False

        rendered = rendered_inline_node(data) if self.inline else rendered_node(data)

        # Copy attributes from pending_node.
        rendered.update_all_atts(self)
        rendered.source, rendered.line = self.source, self.line

        # Adopt the children (which may be system_messages) to the rendered.
        # rendered += self.children
        self.clear()

        # TODO: filter inline

        # if not self.extra.reporter.empty():
        #     rendered += self.extra.reporter

        # Render the data to nodes, then appending them to RenderedNode.
        _caller = _Caller(caller)
        parser = _caller.inline_markup_parser if self.inline else _caller.markup_parser
        rendered += self.template.render(parser, data, extra=self.extra.data)

        if replace:
            if self.seamless:
                self.replace_self(rendered.children)
            else:
                self.replace_self(rendered)

        return rendered


# ======================================
# Extra context register and management.
# ======================================


class ExtraContextGenerator(ABC): ...


class RenderPhaseContextGenerator(ExtraContextGenerator):
    @abstractmethod
    def generate(self, caller: Caller) -> Any: ...


class ParsePhaseContextGenerator(ExtraContextGenerator):
    @abstractmethod
    def generate(self, caller: ParseCaller) -> Any: ...


class TransformPhaseContextGenerator(ExtraContextGenerator):
    @abstractmethod
    def generate(self, caller: TransformCaller) -> Any: ...


class ExtraContextRegistry:
    names: set[str]
    parsing: dict[str, ParsePhaseContextGenerator]
    parsed: dict[str, ParsePhaseContextGenerator]
    post_transform: dict[str, TransformPhaseContextGenerator]
    render: dict[str, RenderPhaseContextGenerator]

    def __init__(self) -> None:
        self.names = set()
        self.parsing = {}
        self.parsed = {}
        self.post_transform = {}
        self.render = {}

    def _name_dedup(self, name: str) -> None:
        # TODO: allow dup
        if name in self.names:
            raise ValueError(f'Context generator {name} already exists')
        self.names.add(name)

    def add_parsing(self, name: str, ctxgen: ParsePhaseContextGenerator) -> None:
        self._name_dedup(name)
        self.parsing['_' + name] = ctxgen

    def add_parsed(self, name: str, ctxgen: ParsePhaseContextGenerator) -> None:
        self._name_dedup(name)
        self.parsed['_' + name] = ctxgen

    def add_post_transform(
        self, name: str, ctxgen: TransformPhaseContextGenerator
    ) -> None:
        self._name_dedup(name)
        self.post_transform['_' + name] = ctxgen

    def add_render(self, name: str, ctxgen: RenderPhaseContextGenerator):
        self._name_dedup(name)
        self.render['_' + name] = ctxgen


EXTRACTX_REGISTRY = ExtraContextRegistry()


class _ExtraContextManager:
    data: dict[str, Any]
    reporter: Reporter

    def __init__(self) -> None:
        self.data = {}
        self.reporter = Reporter('Extra Context Generation Report', 'ERROR')

    def on_rendering(self, caller: Caller) -> None:
        for name, ctxgen in EXTRACTX_REGISTRY.render.items():
            self._safegen(name, lambda: ctxgen.generate(caller))

    def on_parsing(self, caller: ParseCaller) -> None:
        for name, ctxgen in EXTRACTX_REGISTRY.parsing.items():
            self._safegen(name, lambda: ctxgen.generate(caller))

    def on_parsed(self, caller: ParseCaller) -> None:
        for name, ctxgen in EXTRACTX_REGISTRY.parsed.items():
            self._safegen(name, lambda: ctxgen.generate(caller))

    def on_post_transform(self, caller: TransformCaller) -> None:
        for name, ctxgen in EXTRACTX_REGISTRY.post_transform.items():
            self._safegen(name, lambda: ctxgen.generate(caller))

    def _safegen(self, name: str, gen: Callable[[], Any]):
        try:
            # ctxgen.generate can be user-defined code, exception of any kind are possible.
            self.data[name] = gen()
        except Exception:
            self.reporter.text(f'Failed to generate extra context {name}:')
            self.reporter.excption()


# ===============
# Render workflow
# ===============
#
# 1. Define data: BaseDataDefiner generates a pending_node, which contains:
#
#    - Context(Data), Extra contexts
#    - Schema (for verifing Data)
#    - Template
#
# 2. Render data: Some one (Caller) calls pending_node.render during the
#
#    1. On Phase.Parsing: Called by BaseDataDefineDirective and
#       BaseDataDefineRole
#    2. On Phase.Parsed: Called by _ParsedHook.
#    3. On Phase.Resolving: Called by _ResolvingHook.


class BaseDataDefiner(ABC):
    """
    A abstract class that owns :cls:`RawData` and support
    validating and rendering the data at the appropriate time.

    The subclasses *MUST* be subclass of :cls:`SphinxDirective` or
    :cls:`SphinxRole`.
    """

    """Methods to be implemented."""

    @abstractmethod
    def current_raw_data(self) -> RawData: ...

    @abstractmethod
    def current_template(self) -> Template: ...

    @abstractmethod
    def current_schema(self) -> Schema: ...

    """Methods to be overrided."""

    def process_raw_data(self, data: RawData) -> None: ...

    def process_paresd_data(self, data: ParsedData) -> None: ...

    def process_pending_node(self, n: pending_node) -> None: ...

    def process_rendered_node(self, n: RenderedNode) -> None: ...

    """Methods used internal."""

    @final
    def build_pending_node(
        self, data: PendingData | ParsedData | dict[str, Any], tmpl: Template
    ) -> pending_node:
        if isinstance(data, PendingData):
            self.process_raw_data(data.raw)

        pending = pending_node(data, tmpl)

        # Generate and save parsing extra context for later use.
        pending.extra.on_parsing(cast(ParseCaller, self))

        self.process_pending_node(pending)

        return pending

    @final
    def render_pending_node(self, pending: pending_node) -> RenderedNode:
        rendered = pending.render(cast(Caller, self))

        if isinstance(rendered.data, ParsedData):
            self.process_paresd_data(rendered.data)

        self.process_rendered_node(rendered)

        return rendered

    @final
    def render(self) -> list[nodes.Node]:
        data = self.current_raw_data()
        schema = self.current_schema()
        tmpl = self.current_template()

        pendings = []
        ctx = PendingData(data, schema)
        pendings.append(self.build_pending_node(ctx, tmpl))

        ns = []
        for n in pendings:
            if n.template.phase != Phase.Parsing:
                ns.append(n)
            else:
                ns.append(self.render_pending_node(n))

        return ns


class BaseDataDefineDirective(BaseDataDefiner, SphinxDirective):
    @override
    def current_raw_data(self) -> RawData:
        return RawData(
            ' '.join(self.arguments) if self.arguments else None,
            self.options.copy(),
            '\n'.join(self.content) if self.has_content else None,
        )

    @override
    def process_pending_node(self, n: pending_node) -> None:
        self.set_source_info(n)
        n.inline = False

    @override
    def run(self) -> list[nodes.Node]:
        return self.render()


class BaseDataDefineRole(BaseDataDefiner, SphinxRole):
    @override
    def current_raw_data(self) -> RawData:
        return RawData(None, {}, self.text)

    @override
    def process_pending_node(self, n: pending_node) -> None:
        self.set_source_info(n)
        n.inline = True

    @override
    def run(self) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        return self.render(), []


class _ParsedHook(SphinxDirective):
    def run(self) -> list[nodes.Node]:
        logger.warning(f'running parsed hook for doc {self.env.docname}...')

        # Save origin system_message method.
        orig_sysmsg = self.state_machine.reporter.system_message

        for pending in self.state.document.findall(pending_node):
            # Generate and save parsed extra context for later use.
            pending.extra.on_parsed(self)

            if pending.template.phase != Phase.Parsed:
                continue

            # Hook system_message method to let it report the
            # correct line number.
            def fix_lineno(level, message, *children, **kwargs):
                kwargs['line'] = pending.line
                return orig_sysmsg(level, message, *children, **kwargs)

            self.state_machine.reporter.system_message = fix_lineno

            pending.render(self, replace=True)

        # Restore system_message method.
        self.state_machine.reporter.system_message = orig_sysmsg

        return []  # nothing to return


def _insert_parsed_hook(app, docname, content):
    # NOTE: content is a single element list, representing the content of the
    # source file.
    #
    # .. seealso:: https://www.sphinx-doc.org/en/master/extdev/event_callbacks.html#event-source-read
    #
    # TODO: markdown?
    # TODO: rst_prelog?
    content[-1] = content[-1] + '\n\n.. data.parsed-hook::'


class _ResolvingHook(SphinxPostTransform):
    # After resolving pending_xref.
    default_priority = (ReferencesResolver.default_priority or 10) + 5

    def apply(self, **kwargs):
        logger.warning(f'running resolving hook for doc {self.env.docname}...')

        for pending in self.document.findall(pending_node):
            # Generate and save parsed extra context for later use.
            pending.extra.on_post_transform(self)

            if pending.template.phase != Phase.PostTranform:
                # TODO: deal with ValueError
                continue

            pending.render(self, replace=True)


def setup(app: Sphinx) -> None:
    # Hook for Phase.Parsed.
    app.add_directive('data.parsed-hook', _ParsedHook)
    app.connect('source-read', _insert_parsed_hook)

    # Hook for Phase.Resolving.
    app.add_post_transform(_ResolvingHook)
