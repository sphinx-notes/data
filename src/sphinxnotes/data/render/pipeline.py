"""
sphinxnotes.data.pipeline
~~~~~~~~~~~~~~~~~~~~~~~~~

:copyright: Copyright 2026 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.

This modeule defines pipeline for rendering data to nodes.

The Pipline
===========

1. Define data: BaseDataDefiner generates a :cls:`pending_data`, which contains:

   - Data and possible extra contexts
   - Schema for validating Data
   - Template for rendering data to markup text

2. Render data: the ``pending_data`` nodes will be rendered
   (by calling :meth:`pending_node.render`) at some point, depending on :cls:`Phase`.

   The one who calls ``pending_node.render`` is called ``Host``.
   The ``Host`` host is responsible for rendering the markup text into doctree
   nodes (See :cls:`MarkupRenderer`).

   Phases:

   :``Phase.Parsing``:
      Called by BaseDataDefiner ('s subclasses)

   :``Phase.Parsed``:
      Called by :cls:`_ParsedHook`.

   :``Phase.Resolving``:
      Called by :cls:`_ResolvingHook`.

How :cls:`RawData` be rendered ``list[nodes.Node]``
===================================================

1. Schema.parse(RawData) -> ParsedData
2. TemplateRenderer.render(ParsedData) -> Markup Text (``str``)
3. MarkupRenderer.render(Markup Text) -> doctree Nodes (list[nodes.Node])

"""

from __future__ import annotations
from typing import TYPE_CHECKING, override, final, cast
from abc import abstractmethod, ABC

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms.post_transforms import SphinxPostTransform, ReferencesResolver

from .render import Phase, Template, Host, ParseHost
from .datanodes import pending_data, rendered_data
from .extractx import ExtraContextGenerator
from ..data import RawData, PendingData, ParsedData, Field, Schema

if TYPE_CHECKING:
    from typing import Any
    from sphinx.application import Sphinx

logger = logging.getLogger(__name__)


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

    def process_pending_node(self, n: pending_data) -> None: ...

    def process_rendered_node(self, n: rendered_data) -> None: ...

    """Methods used internal."""

    @final
    def build_pending_node(
        self,
        data: PendingData | ParsedData | dict[str, Any],
        tmpl: Template,
    ) -> pending_data:
        if isinstance(data, PendingData):
            self.process_raw_data(data.raw)

        pending = pending_data(data, tmpl)

        # Generate and save parsing phase extra context for later use.
        ExtraContextGenerator(pending).on_parsing(cast(ParseHost, self))

        self.process_pending_node(pending)

        return pending

    @final
    def render_pending_node(self, pending: pending_data) -> rendered_data:
        # Generate and save parsing phase extra context for later use.
        ExtraContextGenerator(pending).on_anytime()

        rendered = pending.render(cast(Host, self))

        if isinstance(rendered.data, ParsedData):
            # FIXME: template are rendered, meanless to procss parsed data.
            self.process_paresd_data(rendered.data)

        self.process_rendered_node(rendered)

        return rendered

    @final
    def render_or_pass(self) -> pending_data | rendered_data:
        """
        If the timing(Phase) is ok, rendering the data to a :cls:`rendered_data`;
        otherwise, returns a :cls:`pending_data node`.
        """
        data = self.current_raw_data()
        schema = self.current_schema()
        tmpl = self.current_template()

        pending = self.build_pending_node(PendingData(data, schema), tmpl)

        if pending.template.phase != Phase.Parsing:
            return pending

        return self.render_pending_node(pending)


class BaseDataDefineDirective(BaseDataDefiner, SphinxDirective):
    @override
    def current_raw_data(self) -> RawData:
        return RawData(
            ' '.join(self.arguments) if self.arguments else None,
            self.options.copy(),
            '\n'.join(self.content) if self.has_content else None,
        )

    @override
    def process_pending_node(self, n: pending_data) -> None:
        self.set_source_info(n)

    @override
    def run(self) -> list[nodes.Node]:
        return [self.render_or_pass()]


class BaseDataDefineRole(BaseDataDefiner, SphinxRole):
    @override
    def current_raw_data(self) -> RawData:
        return RawData(None, {}, self.text)

    @override
    def process_pending_node(self, n: pending_data) -> None:
        self.set_source_info(n)
        n.inline = True

    @override
    def run(self) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        n = self.render_or_pass()
        if isinstance(n, pending_data):
            return [n], []
        return n.inline(parent=self.inliner.parent)


class _ParsedHook(SphinxDirective):
    def run(self) -> list[nodes.Node]:
        logger.warning(f'running parsed hook for doc {self.env.docname}...')

        # Save origin system_message method.
        orig_sysmsg = self.state_machine.reporter.system_message

        for pending in self.state.document.findall(pending_data):
            # Generate and save parsed extra context for later use.
            ExtraContextGenerator(pending).on_parsed(cast(ParseHost, self))

            if pending.template.phase != Phase.Parsed:
                continue

            # Hook system_message method to let it report the
            # correct line number.
            def fix_lineno(level, message, *children, **kwargs):
                kwargs['line'] = pending.line
                return orig_sysmsg(level, message, *children, **kwargs)

            self.state_machine.reporter.system_message = fix_lineno

            # Generate and save render phase extra contexts for later use.
            ExtraContextGenerator(pending).on_anytime()

            rendered = pending.render(self)

            if pending.inline:
                pending.replace_self_inline(rendered)
            else:
                pending.replace_self(rendered)

        # Restore system_message method.
        self.state_machine.reporter.system_message = orig_sysmsg

        return []  # nothing to return


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
            '%sStrictDataDefineDirective' % name.title(),
            (cls,),
            {
                'schema': schema,
                'template': tmpl,
                'has_content': has_content,
                'required_arguments': required_arguments,
                'optional_arguments': optional_arguments,
                'option_spec': option_spec,
            },
        )


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

        for pending in self.document.findall(pending_data):
            # Generate and save parsed extra context for later use.
            ExtraContextGenerator(pending).on_post_transform(self)

            if pending.template.phase != Phase.PostTranform:
                continue

            # Generate and save render phase extra contexts for later use.
            ExtraContextGenerator(pending).on_anytime()

            rendered = pending.render(self)

            if pending.inline:
                pending.replace_self_inline(rendered)
            else:
                pending.replace_self(rendered)


def setup(app: Sphinx) -> None:
    # Hook for Phase.Parsed.
    app.add_directive('data.parsed-hook', _ParsedHook)
    app.connect('source-read', _insert_parsed_hook)

    # Hook for Phase.Resolving.
    app.add_post_transform(_ResolvingHook)
