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
from .render import (
    pending_data,
    rendered_data,
    BaseDataDefineRole,
    BaseDataDefineDirective,
    StrictDataDefineDirective,
)
from .render.template import Template
from .render.renderer import Host
from .render.extractx import ExtraContextRegistry, ExtraContextGenerator
from .config import Config

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
    'Host',
    'pending_data',
    'rendered_data',
    'rendered_data',
    'BaseDataDefineRole',
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
    def extra_context(cls) -> ExtraContextRegistry:
        return ExtraContextGenerator.registry


REGISTRY = Registry()


def setup(app: Sphinx):
    meta.pre_setup(app)

    from . import config, render, adhoc
    from .render import template

    config.setup(app)
    template.setup(app)
    render.setup(app)
    adhoc.setup(app)

    return meta.post_setup(app)
