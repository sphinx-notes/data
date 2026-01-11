from __future__ import annotations
from typing import Any

from docutils import nodes
from sphinx.util.docutils import SphinxDirective, SphinxRole
from sphinx.transforms import SphinxTransform

from .utils import find_current_document, find_current_section
from .utils.context_proxy import proxy


def markup(v: SphinxDirective | SphinxRole | nodes.Element) -> dict[str, Any]:
    ctx = {}

    if isinstance(v, nodes.Element):
        ctx['_markup'] = {}
    else:
        isdir = isinstance(v, SphinxDirective)
        ctx['_markup'] = {
            'type': 'directive' if isdir else 'role',
            'name': v.name,
            'lineno': v.lineno,
            'rawtext': v.block_text if isdir else v.rawtext,
        }
    return ctx


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
