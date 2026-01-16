from __future__ import annotations
from typing import TYPE_CHECKING

from docutils import nodes

from .utils import find_current_document, find_current_section
from .utils.context_proxy import proxy
from .render import EXTRACTX_REGISTRY
from .template import Phase

if TYPE_CHECKING:
    from typing import Any
    from sphinx.transforms import SphinxTransform
    from sphinx.util.docutils import SphinxDirective, SphinxRole


def markup(v: SphinxDirective | SphinxRole) -> dict[str, Any]:
    isdir = isinstance(v, SphinxDirective)
    return {
        'type': 'directive' if isdir else 'role',
        'name': v.name,
        'lineno': v.lineno,
        'rawtext': v.block_text if isdir else v.rawtext,
    }

def doctree(v: SphinxDirective | SphinxRole | nodes.Node) -> dict[str, Any]:
    ctx = {}
    if isinstance(v, nodes.Node):
        ctx['_doc'] = proxy(find_current_document(v))
        ctx['_section'] = proxy(find_current_section(v))
    else:
        isdir = isinstance(v, SphinxDirective)
        state = v.state if isdir else v.inliner
        ctx['_doc'] = proxy(state.document)
        ctx['_section'] = proxy(find_current_section(state.parent))
    return ctx


def sphinx(v: SphinxDirective | SphinxRole | SphinxTransform) -> dict[str, Any]:
    ctx = {}
    ctx['_env'] = proxy(v.env)
    ctx['_config'] = proxy(v.config)
    return ctx

EXTRACTX_REGISTRY.add_parse_generator(Phase.Parsing, markup)
