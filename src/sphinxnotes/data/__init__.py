"""
sphinxnotes.data
~~~~~~~~~~~~~~~~

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from sphinx.util import logging

from . import meta
from .data import (
    Registry as DataRegistry,
    REGISTRY as DATA_REGISTRY,
    PlainValue,
    Value,
    ValueWrapper,
    RawData,
    ParsedData,
    Field,
    Schema,
)
from .template import Phase, Template
from .render import (
    Caller,
    pending_node,
    rendered_node,
    BaseDataDefiner,
    BaseDataDefineRole,
    BaseDataDefineDirective,
    ExtraContextRegistry,
    EXTRACTX_REGISTRY,
)
from .derive import StrictDataDefineDirective
from .config import Config
from . import extractx

if TYPE_CHECKING:
    from sphinx.application import Sphinx


"""Python API for other Sphinx extesions."""
__all__ = [
    'Config',
    'Registry',
    'PlainValue',
    'Value',
    'ValueWrapper',
    'RawData',
    'ParsedData',
    'Field',
    'Schema',
    'Phase',
    'Template',
    'Caller',
    'pending_node',
    'rendered_node',
    'rendered_node',
    'BaseDataDefiner',
    'BaseDataDefineRole',
    'BaseDataDefineDirective',
    'BaseDataDefineDirective',
    'StrictDataDefineDirective',
]

logger = logging.getLogger(__name__)


class Registry:
    """The global, all-in-one registry for user."""

    @property
    def data(self) -> DataRegistry:
        return DATA_REGISTRY

    @property
    def extractx(cls) -> ExtraContextRegistry:
        return EXTRACTX_REGISTRY


REGISTRY = Registry()


def setup(app: Sphinx):
    meta.pre_setup(app)

    from . import config, template, render, adhoc

    config.setup(app)
    template.setup(app)
    render.setup(app)
    adhoc.setup(app)

    return meta.post_setup(app)
