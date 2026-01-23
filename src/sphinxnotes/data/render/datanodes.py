from __future__ import annotations
from typing import TYPE_CHECKING
from pprint import pformat

from docutils import nodes
from docutils.parsers.rst.states import Inliner

from .render import Template
from .markup import MarkupRenderer
from .template import TemplateRenderer
from ..data import RawData, PendingData, ParsedData
from ..utils import (
    Unpicklable,
    Report,
    Reporter,
    find_current_document,
    find_nearest_block_element,
)
from ..config import Config

if TYPE_CHECKING:
    from typing import Any, Callable
    from .markup import Host


class Base(nodes.Element): ...


class pending_node(Base, Unpicklable):
    # The data to be rendered by Jinja template.
    data: PendingData | ParsedData | dict[str, Any]
    # The extra context for Jina template.
    extra: dict[str, Any]
    #: Jinja template for rendering the context.
    template: Template
    #: Whether rendering to inline nodes.
    inline: bool

    def __init__(
        self,
        data: PendingData | ParsedData | dict[str, Any],
        tmpl: Template,
        inline: bool = False,
        rawsource='',
        *children,
        **attributes,
    ) -> None:
        super().__init__(rawsource, *children, **attributes)
        self.data = data
        self.extra = {}
        self.template = tmpl
        self.inline = inline

        # Init hook lists.
        self._raw_data_hooks = []
        self._parsed_data_hooks = []
        self._markup_text_hooks = []
        self._rendered_nodes_hooks = []

    def render(self, host: Host) -> rendered_node:
        """
        The core function for rendering data to docutils nodes.

        1. Schema.parse(RawData) -> ParsedData
        2. TemplateRenderer.render(ParsedData) -> Markup Text (``str``)
        3. MarkupRenderer.render(Markup Text) -> doctree Nodes (list[nodes.Node])
        """
        # 0. Create container for rendered nodes.
        rendered = rendered_node()
        # Copy attributes from pending_node.
        rendered.update_all_atts(self)
        # Copy source and line (which are not included in update_all_atts).
        rendered.source, rendered.line = self.source, self.line
        # Copy the pending's children to the rendered.
        rendered[:0] = [x.deepcopy() for x in self.children]

        report = Report(
            'Render Debug Report', 'DEBUG', source=self.source, line=self.line
        )

        # 1. Prepare context for Jinja template.
        if isinstance(self.data, PendingData):
            report.text('Raw data:')
            report.code(pformat(self.data.raw), lang='python')
            report.text('Schema:')
            report.code(pformat(self.data.schema), lang='python')

            try:
                data = self.data.parse()
            except ValueError:
                report.text('Failed to parse raw data:')
                report.excption()
                rendered += report
                return rendered
        else:
            data = self.data

        rendered.data = data

        report.text('Parsed data:')
        report.code(pformat(data), lang='python')
        report.text('Extra context (just key):')
        report.code(pformat(list(self.extra.keys())), lang='python')
        report.text('Template:')
        report.code(self.template.text, lang='jinja')

        # 2. Render the template and data to markup text.
        try:
            markup = TemplateRenderer(self.template.text).render(data, extra=self.extra)
        except Exception:  # TODO: what excetpion?
            report.text('Failed to render Jinja template:')
            report.excption()
            rendered += report
            return rendered

        report.text('Rendered markup text:')
        report.code(markup, lang='rst')

        # 3. Render the markup text to doctree nodes.
        try:
            ns, msgs = MarkupRenderer(host).render(markup, inline=self.inline)
        except Exception:
            report.text(
                'Failed to render markup text '
                f'to {"inline " if self.inline else ""}nodes:'
            )
            report.excption()
            rendered += report
            return rendered

        report.text(f'Rendered nodes (inline: {self.inline}):')
        report.code('\n\n'.join([n.pformat() for n in ns]), lang='xml')
        if msgs:
            report.text('Systemd messages:')
            for msg in msgs:
                report.node(msg)

        # 4. Add rendered nodes to container.
        rendered += ns

        if self.template.debug or Config.render_debug:
            rendered += report

        # Clear all empty reports before returning.
        Reporter(rendered).clear_empty()

        return rendered

    def replace_self_inline(
        self, rendered: rendered_node, inliner: Report.Inliner
    ) -> None:
        # Split inline nodes and system_message noeds from rendered_node node.
        ns, msgs = rendered.inline(inliner)

        # Insert reports to nearst block elements (usually nodes.paragraph).
        blkparent = find_nearest_block_element(self.parent) or find_current_document(
            self
        )
        assert blkparent
        blkparent += msgs

        # Replace self with inline nodes.
        self.replace_self(ns)

    """Hooks for procssing render intermediate products. """

    type RawDataHook = Callable[[pending_node, RawData], None]
    type ParsedDataHook = Callable[[pending_node, RawData], None]
    type MarkupTextHook = Callable[[pending_node, str], None]
    type RenderedNodesHook = Callable[
        [pending_node, list[nodes.Node], list[nodes.system_message]], None
    ]

    _raw_data_hooks: list[RawDataHook]
    _parsed_data_hooks: list[ParsedDataHook]
    _markup_text_hooks: list[MarkupTextHook]
    _rendered_nodes_hooks: list[RenderedNodesHook]

    def process_raw_data(self, hook: RawDataHook) -> None:
        self._raw_data_hooks.append(hook)

    def process_parsed_data(self, hook: ParsedDataHook) -> None:
        self._parsed_data_hooks.append(hook)

    def process_markup_text(self, hook: MarkupTextHook) -> None:
        self._markup_text_hooks.append(hook)

    def process_rendered_nodes(self, hook: RenderedNodesHook) -> None:
        self._rendered_nodes_hooks.append(hook)


class rendered_node(Base, nodes.container):
    # The data used when rendering this node.
    data: ParsedData | dict[str, Any] | None

    def inline(
        self,
        inliner: Inliner | tuple[nodes.document, nodes.Element],
    ) -> tuple[list[nodes.Node], list[nodes.system_message]]:
        # Report (nodes.system_message subclass) is not inline node,
        # should be removed before inserting to doctree.
        reports = Reporter(self).clear()
        for report in reports:
            self.append(report.problematic(inliner))

        children = self.children
        self.clear()

        return children, [x for x in reports]
