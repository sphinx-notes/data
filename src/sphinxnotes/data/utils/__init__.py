from typing import TypeVar, cast, Literal as Lit

from docutils import nodes
from docutils.frontend import get_default_settings
from docutils.parsers.rst import Parser
from docutils.parsers.rst.states import Struct
from docutils.utils import new_document
from sphinx.util import logging
from sphinx.util.docutils import SphinxRole

logger = logging.getLogger(__name__)


def parse_text_to_nodes(text: str) -> list[nodes.Node]:
    """
    Utility for parsing standard reStructuredText (without Sphinx stuffs) to nodes.
    Used when there is not a SphinxDirective/SphinxRole available.
    """
    # TODO: markdown support
    document = new_document('<string>', settings=get_default_settings(Parser))  # type: ignore
    Parser().parse(text, document)
    return document.children


def role_parse_text_to_nodes(self: SphinxRole, text: str) -> list[nodes.Node]:
    """
    Utility for parsing reStructuredText (without Sphinx stuffs) to nodes in
    SphinxRole Context.
    """
    memo = Struct(
        document=self.inliner.document,
        reporter=self.inliner.reporter,
        language=self.inliner.language,
    )
    ns, msgs = self.inliner.parse(text, self.lineno, memo, self.inliner.parent)
    return ns + msgs


_Node = TypeVar('_Node', bound=nodes.Node)


def find_parent(node: nodes.Node | None, typ: type[_Node]) -> _Node | None:
    if node is None or isinstance(node, typ):
        return node
    return find_parent(node.parent, typ)


def find_current_section(node: nodes.Node | None) -> nodes.section | None:
    return find_parent(node, nodes.section)


def find_current_document(node: nodes.Node | None) -> nodes.document | None:
    return find_parent(node, nodes.document)


def find_first_child(node: nodes.Element, cls: type[_Node]) -> _Node | None:
    if (index := node.first_child_matching_class(cls)) is None:
        return None
    return cast(_Node, node[index])


def find_titular_node_upward(node: nodes.Element | None) -> nodes.Element | None:
    if node is None:
        return None
    if isinstance(node, (nodes.section, nodes.sidebar)):
        if title := find_first_child(node, nodes.title):
            return title
    if isinstance(node, nodes.definition_list_item):
        if term := find_first_child(node, nodes.term):
            return term
    if isinstance(node, nodes.field):
        if field := find_first_child(node, nodes.field_name):
            return field
    if isinstance(node, nodes.list_item):
        if para := find_first_child(node, nodes.paragraph):
            return para
    return find_titular_node_upward(node.parent)


class Reporter(nodes.system_message):
    def __init__(
        self,
        title: str,
        level: Lit['DEBUG'] | Lit['INFO'] | Lit['WARNING'] | Lit['ERROR'] = 'DEBUG',
    ) -> None:
        super().__init__(title + ':', type=level, level=2, source='')
        # logger.warning(f'creating a new report: {title}')

    def append_text(self, text: str) -> None:
        self += nodes.paragraph(text, text)
        # logger.warning(f'report append text: {text}')

    def append_code(self, code: str, lang: str | None = None) -> None:
        blk = nodes.literal_block(code, code)
        if lang:
            blk['language'] = lang
        self += blk
        # logger.warning(f'report append code: {code}')
