"""
sphinxnotes.data.render
~~~~~~~~~~~~~~~~~~~~~~~

Module for rendering data to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from pprint import pformat
from typing import TYPE_CHECKING, override, final, cast
from abc import abstractmethod, ABC

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms.post_transforms import SphinxPostTransform, ReferencesResolver

from ..data import RawData, PendingData, ParsedData, Field, Schema
from ..utils import Report, find_nearest_block_element
from .nodes import pending_data, rendered_data, Phase
from .renderer import Renderer, Host, ParseHost, HostWrapper
from .extractx import ExtraContextGenerator
from .reporter import Reporter
from .template import Template

if TYPE_CHECKING:
    from typing import Any
    from sphinx.application import Sphinx

logger = logging.getLogger(__name__)


def render(host: Host, pending: pending_data) -> rendered_data:
    """The core render function."""
    # 0. Create container for rendered nodes.
    rendered = rendered_data()
    # Copy attributes from pending_node.
    rendered.update_all_atts(pending)
    # Copy source and line (which are not included in update_all_atts).
    rendered.source, rendered.line = pending.source, pending.line

    report = Report(
        'Render Debug Report', 'DEBUG', source=pending.source, line=pending.line
    )

    # 1. Prepare context for Jinja template.
    if isinstance(pending.data, PendingData):
        report.text('Raw data:')
        report.code(pformat(pending.data.raw), lang='python')
        report.text('Schema:')
        report.code(pformat(pending.data.schema), lang='python')

        try:
            data = pending.data.parse()
        except ValueError:
            report.text('Failed to parse raw data:')
            report.excption()
            rendered += report
            return rendered
    else:
        data = pending.data

    rendered.data = data

    report.text('Parsed data:')
    report.code(pformat(data), lang='python')
    report.text('Extra context (just key):')
    report.code(pformat(list(pending.extra.keys())), lang='python')
    report.text('Template:')
    report.code(pending.template, lang='jinja')

    # 2. Render the template and data to markup text.
    try:
        text = Template(pending.template).render(data, extra=pending.extra)
    except Exception:  # TODO: what excetpion?
        report.text('Failed to render Jinja template:')
        report.excption()
        rendered += report
        return rendered

    report.text('Rendered markup text:')
    report.code(text, lang='rst')

    # 3. Render the markup text to doctree nodes.
    try:
        ns, msgs = Renderer(host).render(text, inline=pending.inline)
    except Exception:
        report.text(
            'Failed to render markup text '
            f'to {"inline " if pending.inline else ""}nodes:'
        )
        report.excption()
        rendered += report
        return rendered

    report.text('Rendered nodes:')
    report.code('\n\n'.join([n.pformat() for n in ns]), lang='xml')
    if msgs:
        report.text('Systemd messages:')
        for msg in msgs:
            report.node(msg)

    # 4. Add rendered nodes to container.
    rendered += ns

    if pending.debug:
        rendered += report

    # Clear all empty reports.
    Reporter(rendered).clear_empty()

    return rendered


def replace(host: Host, pending: pending_data, rendered: rendered_data) -> None:
    """Replace the pending data node with rendered data node."""

    assert pending.parent

    # Clear all empty reports.
    Reporter(pending).clear_empty()
    # Adopt the pending's children to the rendered.
    rendered[:0] = pending.children
    # Clear all children.
    pending.clear()

    if pending.inline:
        doc = HostWrapper(host).doctree
        # Report(nodes.system_message subclass) is not inline node,
        # should be removed before inserting to doctree.
        reports = Reporter(rendered).clear()
        for report in reports:
            rendered.append(report.problematic((doc, pending.parent)))
        if parent := find_nearest_block_element(pending.parent) or doc:
            parent += reports

    if replace:
        if pending.inline:
            # NOTE: rendered_node can not be inlined too.
            newnodes = rendered.children
            rendered.clear()
        else:
            newnodes = rendered
        pending.replace_self(newnodes)


# ===============
# Render workflow
# ===============
#
# 1. Define data: BaseDataDefiner generates a pending_node, which contains:
#
#    - Data and extra contexts
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

    def process_pending_node(self, n: pending_data) -> None: ...

    def process_rendered_node(self, n: rendered_data) -> None: ...

    """Methods used internal."""

    @final
    def build_pending_node(
        self,
        data: PendingData | ParsedData | dict[str, Any],
        tmpl: str,
        phase: Phase,
    ) -> pending_data:
        if isinstance(data, PendingData):
            self.process_raw_data(data.raw)

        pending = pending_data(data, tmpl, phase)

        # Generate and save parsing phase extra context for later use.
        ExtraContextGenerator(pending).on_parsing(cast(ParseHost, self))

        self.process_pending_node(pending)

        return pending

    @final
    def render_pending_node(self, pending: pending_data) -> rendered_data:
        host = cast(Host, self)

        # Generate and save parsing phase extra context for later use.
        ExtraContextGenerator(pending).on_rendering(host)

        rendered = render(host, pending)

        if isinstance(rendered.data, ParsedData):
            self.process_paresd_data(rendered.data)

        self.process_rendered_node(rendered)

        return rendered

    @final
    def try_render(self) -> pending_data | rendered_data:
        data = self.current_raw_data()
        schema = self.current_schema()
        tmpl = self.current_template()
        phase = Phase.default()

        data = PendingData(data, schema)
        pending = self.build_pending_node(data, tmpl.text, phase)

        if phase != Phase.Parsing:
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
        n.inline = False

    @override
    def run(self) -> list[nodes.Node]:
        return [self.try_render()]


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
        n = self.try_render()
        if isinstance(n, pending_data):
            return [n], []

        reports = Reporter(n).clear()
        ns = n.children.copy()
        n.clear()

        for report in reports:
            prb = report.problematic(self.inliner)
            ns.append(prb)

        return ns, reports


class _ParsedHook(SphinxDirective):
    def run(self) -> list[nodes.Node]:
        logger.warning(f'running parsed hook for doc {self.env.docname}...')

        # Save origin system_message method.
        orig_sysmsg = self.state_machine.reporter.system_message

        for pending in self.state.document.findall(pending_data):
            # Generate and save parsed extra context for later use.
            ExtraContextGenerator(pending).on_parsed(cast(ParseHost, self))

            if pending.phase != Phase.Parsed:
                continue

            # Hook system_message method to let it report the
            # correct line number.
            def fix_lineno(level, message, *children, **kwargs):
                kwargs['line'] = pending.line
                return orig_sysmsg(level, message, *children, **kwargs)

            self.state_machine.reporter.system_message = fix_lineno

            # Generate and save render phase extra contexts for later use.
            ExtraContextGenerator(pending).on_rendering(self)

            rendered = render(self, pending)
            replace(pending, rendered)

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

            if pending.phase != Phase.PostTranform:
                continue

            # Generate and save render phase extra contexts for later use.
            ExtraContextGenerator(pending).on_rendering(self)

            rendered = render(self, pending)
            replace(self, pending, rendered)


def setup(app: Sphinx) -> None:
    # Hook for Phase.Parsed.
    app.add_directive('data.parsed-hook', _ParsedHook)
    app.connect('source-read', _insert_parsed_hook)

    # Hook for Phase.Resolving.
    app.add_post_transform(_ResolvingHook)
