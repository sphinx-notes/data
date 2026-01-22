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

.. seealso:: :meth:`.datanodes.pending_data.render`.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, override, final, cast
from abc import abstractmethod, ABC

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms.post_transforms import SphinxPostTransform, ReferencesResolver

from .render import Phase, Template, Host, ParseHost, TransformHost
from .datanodes import pending_data, rendered_data
from .extractx import ExtraContextGenerator
from ..data import RawData, PendingData, ParsedData, Field, Schema

if TYPE_CHECKING:
    from typing import Any
    from sphinx.application import Sphinx

logger = logging.getLogger(__name__)


class Pipeline(ABC):
    #: Queue of pending node to be rendered.
    _q: list[pending_data] | None = None

    """Methods to be overrided."""

    def process_pending_node(self, n: pending_data) -> bool:
        """
        You can add hooks to pending node here.

        Return ``true`` if you want to render the pending node *immediately*,
        otherwise it will be inserted to doctree directly andwaiting to later
        rendering
        """
        ...

    def process_rendered_node(self, n: rendered_data) -> None: ...

    """Helper method for subclasses."""

    @final
    def queue(self, n: pending_data) -> None:
        if not self._q:
            self._q = []
        self._q.append(n)

    @final
    def queue_raw_data(
        self, data: RawData, schema: Schema, tmpl: Template
    ) -> pending_data:
        pending = pending_data(PendingData(data, schema), tmpl)
        self.queue(pending)
        return pending

    @final
    def queue_parsed_data(self, data: ParsedData, tmpl: Template) -> pending_data:
        pending = pending_data(data, tmpl)
        self.queue(pending)
        return pending

    @final
    def queue_any_data(self, data: Any, tmpl: Template) -> pending_data:
        pending = pending_data(data, tmpl)
        self.queue(pending)
        return pending

    @final
    def render_queue(self) -> list[pending_data | rendered_data]:
        """
        Try rendering all pending nodes in queue.

        If the timing(Phase) is ok, :cls:`pending_data` will be rendered to a
        :cls:`rendered_data`; otherwise, the pending node is unchanged.

        If the pending node is already inserted to document, it will not be return.
        And the corrsponding rendered node will replace it too.
        """

        ns = []
        while self._q:
            pending = self._q.pop()

            if not self.process_pending_node(pending):
                ns.append(pending)
                continue

            # Generate global extra context for later use.
            ExtraContextGenerator(pending).on_anytime()

            rendered = pending.render(cast(Host, self))
            self.process_rendered_node(rendered)

            if not pending.parent:
                ns.append(rendered)
                continue

            if pending.inline:
                pending.replace_self_inline(rendered)
            else:
                pending.replace_self(rendered)

        return ns


class BaseDataDefiner(Pipeline):
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

    """Methods override from parent."""

    @override
    def process_pending_node(self, n: pending_data) -> bool:
        host = cast(ParseHost, self)

        # Set source and line.
        host.set_source_info(n)
        # Generate and save parsing phase extra context for later use.
        ExtraContextGenerator(n).on_parsing(host)

        return n.template.phase == Phase.Parsing


class BaseDataDefineDirective(BaseDataDefiner, SphinxDirective):
    @override
    def run(self) -> list[nodes.Node]:
        data = RawData(
            ' '.join(self.arguments) if self.arguments else None,
            self.options.copy(),
            '\n'.join(self.content) if self.has_content else None,
        )
        schema = self.current_schema()
        tmpl = self.current_template()
        self.queue_raw_data(data, schema, tmpl)

        return [x for x in self.render_queue()]


class BaseDataDefineRole(BaseDataDefiner, SphinxRole):
    @override
    def process_pending_node(self, n: pending_data) -> bool:
        n.inline = True
        return super().process_pending_node(n)

    @override
    def run(self) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        data = RawData(None, {}, self.text)
        schema = self.current_schema()
        tmpl = self.current_template()
        self.queue_raw_data(data, schema, tmpl)

        ns, msgs = [], []
        for n in self.render_queue():
            if not isinstance(n, rendered_data):
                ns.append(n)
                continue
            n, msg = n.inline(parent=self.inliner.parent)
            ns += n
            msgs += msg

        return ns, msgs


class _ParsedHook(SphinxDirective, Pipeline):
    @override
    def process_pending_node(self, n: pending_data) -> bool:
        self.state.document.note_source(n.source, n.line)  # type: ignore[arg-type]

        # Generate and save parsed extra context for later use.
        ExtraContextGenerator(n).on_parsed(cast(ParseHost, self))

        return n.template.phase == Phase.Parsed

    @override
    def run(self) -> list[nodes.Node]:
        logger.warning(f'running parsed hook for doc {self.env.docname}...')

        for pending in self.state.document.findall(pending_data):
            self.queue(pending)
            # Hook system_message method to let it report the
            # correct line number.
            # TODO: self.state.document.note_source(source, line)  # type: ignore[arg-type]
            # def fix_lineno(level, message, *children, **kwargs):
            #     kwargs['line'] = pending.line
            #     return orig_sysmsg(level, message, *children, **kwargs)

            # self.state_machine.reporter.system_message = fix_lineno

        ns = self.render_queue()
        assert len(ns) == 0

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


class _ResolvingHook(SphinxPostTransform, Pipeline):
    # After resolving pending_xref.
    default_priority = (ReferencesResolver.default_priority or 10) + 5

    @override
    def process_pending_node(self, n: pending_data) -> bool:
        # Generate and save post transform extra context for later use.
        ExtraContextGenerator(n).on_post_transform(cast(TransformHost, self))

        return n.template.phase == Phase.PostTranform

    @override
    def apply(self, **kwargs):
        logger.warning(f'running resolving hook for doc {self.env.docname}...')

        for pending in self.document.findall(pending_data):
            self.queue(pending)

        ns = self.render_queue()
        assert len(ns) == 0


def setup(app: Sphinx) -> None:
    # Hook for Phase.Parsed.
    app.add_directive('data.parsed-hook', _ParsedHook)
    app.connect('source-read', _insert_parsed_hook)

    # Hook for Phase.Resolving.
    app.add_post_transform(_ResolvingHook)
