"""
sphinxnotes.data.render
~~~~~~~~~~~~~~~~~~~~~~~

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, override, final
from abc import abstractmethod, ABC
from dataclasses import dataclass

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform
from sphinx.transforms.post_transforms import ReferencesResolver


from .data import Field, Schema, RawData, Data
from .template import Template, Phase
from . import extra_contexts
from . import utils

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.environment import BuildEnvironment
    from .template import MarkupParser

logger = logging.getLogger(__name__)


# Possible caller of :meth:`Pending.render`.
# TODO: support Any?
type Caller = SphinxDirective | SphinxRole | SphinxTransform


@dataclass
class _Caller:
    v: Caller

    @property
    def env(self) -> BuildEnvironment:
        return self.v.env

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
                return utils.role_parse_text_to_nodes(self.v, text)

            return wrapper
        else:
            return utils.parse_text_to_nodes

    @property
    def parent_node(self) -> nodes.Element | None:
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
# ===============


class BaseNode(nodes.Element): ...


class RenderedNode(BaseNode):
    data: Data
    external_name: nodes.Node | None
    external_content: list[nodes.Node]


class rendered_node(RenderedNode, nodes.container): ...


class rendered_inline_node(RenderedNode, nodes.inline): ...


class pending_node(BaseNode, nodes.Invisible, nodes.Element):
    data: RawData
    template: Template
    schema: Schema

    inline: bool = False
    need_external_name: bool = False
    need_external_content: bool = False

    def render(self, caller: Caller, replace: bool = False) -> RenderedNode:
        rendered = rendered_inline_node() if self.inline else rendered_node()
        rendered.update_all_atts(self)

        _caller = _Caller(caller)
        # Resolve external name and content.
        if not self.data.name and self.need_external_name:
            if ns := self._resolve_external_name(_caller.parent_node):
                self.data.name = ns.astext()
                rendered.external_name = ns
        if not self.data.content and self.need_external_content:
            if ns := self._resolve_external_content():
                self.data.content = '\n\n'.join([x.astext() for x in ns])
                rendered.external_content = ns

        try:
            data = self.schema.parse(self.data)
        except ValueError as e:
            if isinstance(caller, SphinxDirective):
                raise caller.error(str(e))
            else:
                raise e
            # raise self._caller_exception_hanlder(caller, e)
        else:
            rendered.data = data

        rendered += self.template.render(
            _caller.markup_parser,
            data,
            {
                **extra_contexts.sphinx(caller),
                **extra_contexts.doctree(self),
                **extra_contexts.markup(self),
            },
        )
        # TODO: check tmpl schema line no

        if replace:
            self.replace_self(rendered)

        return rendered

    def _resolve_external_name(
        self, caller_parent: nodes.Element | None
    ) -> nodes.Node | None:
        # NOTE: the pending_data_node may be just created and haven't inserted
        # to doctree (on Phase.Parsing).
        return utils.find_titular_node_upward(self.parent or caller_parent)

    def _resolve_external_content(self) -> list[nodes.Node]:
        if not self.parent:
            return []  # TODO
        contnodes = []
        for i, child in enumerate(self.parent):
            if child == self:
                contnodes = self.parent[i:]
                break
        return contnodes


class BaseDataDefiner(ABC):
    """
    A abstract class that owns :cls:`RawData` and support
    validating and rendering the data at the appropriate time.

    The subclasses *MUST* be subclass of :cls:`SphinxDirective` or
    :cls:`SphinxRole`.
    """

    """Methods to be implemented."""

    @abstractmethod
    def current_template(self) -> Template: ...

    @abstractmethod
    def current_schema(self) -> Schema: ...

    @abstractmethod
    def current_raw_data(self) -> RawData: ...

    """Methods to be overrided."""

    def process_raw_data(self, data: RawData) -> None: ...

    def process_paresd_data(self, data: Data) -> None: ...

    def process_pending_node(self, n: pending_node) -> None: ...

    def process_rendered_node(self, n: RenderedNode) -> None: ...

    """Methods used internal."""

    @final
    def build_pending_node(self) -> pending_node:
        tmpl = self.current_template()
        schema = self.current_schema()
        data = self.current_raw_data()

        self.process_raw_data(data)

        pending = pending_node()
        pending.data, pending.template, pending.schema = data, tmpl, schema
        self.process_pending_node(pending)

        return pending

    @final
    def render_pending_node(self, pending: pending_node) -> RenderedNode:
        rendered = pending.render(self)  # FIXME: type hint
        self.process_paresd_data(rendered.data)
        self.process_rendered_node(rendered)

        return rendered


class BaseDataDefineDirective(BaseDataDefiner, SphinxDirective):
    @override
    def current_raw_data(self) -> RawData:
        return RawData(
            self.arguments[0] if self.arguments else None,
            self.options.copy(),
            '\n'.join(self.content) if self.has_content else None,
        )

    @override
    def process_pending_node(self, n: pending_node) -> None:
        self.set_source_info(n)
        n.inline = False

    @override
    def run(self) -> list[nodes.Node]:
        pending = self.build_pending_node()
        if pending.template.phase != Phase.Parsing:
            return [pending]
        rendered = self.render_pending_node(pending)
        return [rendered]


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
        pending = self.build_pending_node()
        if pending.template.phase != Phase.Parsing:
            return [pending], []
        rendered = self.render_pending_node(pending)
        return [rendered], []


class StrictDataDefineDirective(BaseDataDefineDirective):
    final_argument_whitespace = True

    schema: Schema
    template: Template

    @override
    def current_template(self) -> Template:
        return self.template

    @override
    def current_schema(self) -> Schema:
        return self.schema

    @classmethod
    def derive(
        cls, name: str, schema: Schema, tmpl: Template
    ) -> type[StrictDataDefineDirective]:
        """Generate an AnyDirective child class for describing object."""
        if not schema.name:
            required_arguments = 0
            optional_arguments = 0
        elif schema.name.required:
            required_arguments = 1
            optional_arguments = 0
        else:
            required_arguments = 0
            optional_arguments = 1

        assert not isinstance(schema.attrs, Field)
        option_spec = {}
        for name, field in schema.attrs.items():
            if field.required:
                option_spec[name] = directives.unchanged_required
            else:
                option_spec[name] = directives.unchanged

        has_content = schema.content is not None

        # Generate directive class
        return type(
            '%sStrictDataDirective' % name.title(),
            (StrictDataDefineDirective,),
            {
                'schema': schema,
                'template': tmpl,
                'has_content': has_content,
                'required_arguments': required_arguments,
                'optional_arguments': optional_arguments,
                'option_spec': option_spec,
            },
        )


class _ParsedHook(SphinxDirective):
    def run(self) -> list[nodes.Node]:
        logger.warning(f'running parsed hook for doc {self.env.docname}...')

        # Save origin system_message method.
        orig_sysmsg = self.state_machine.reporter.system_message

        for pending in self.state.document.findall(pending_node):
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


class _ResolvingHook(SphinxTransform):
    # After resolving pending_xref.
    default_priority = (ReferencesResolver.default_priority or 10) + 1

    def apply(self, **kwargs):
        logger.warning(f'running resolving hook for doc {self.env.docname}...')

        for pending in self.document.findall(pending_node):
            if pending.template.phase != Phase.Resolving:
                # TODO: deal with ValueError
                continue

            pending.render(self, replace=True)


def setup(app: Sphinx) -> None:
    # Hook for Phase.Parsed.
    app.add_directive('data.parsed-hook', _ParsedHook)
    app.connect('source-read', _insert_parsed_hook)

    # Hook for Phase.Resolving.
    app.add_transform(_ResolvingHook)
