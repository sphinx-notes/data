"""
sphinxnotes.data.api
~~~~~~~~~~~~~~~~~~~~

Python API for other Sphinx extesions.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from .data import RawData, Value, ValueWrapper, Data, Field, Schema

RawData = RawData
Value = Value
ValueWrapper = ValueWrapper
Data = Data
Field = Field
Schema = Schema

from .template import Phase, Template

Phase = Phase
Template = Template

from .render import Caller, pending_node, RenderedNode, rendered_node, rendered_inline_node, BaseDataDefiner, BaseDataDefineRole, BaseDataDefineDirective, StrictDataDefineDirective

Caller = Caller
pending_node = pending_node
RenderedNode = RenderedNode
rendered_node = rendered_node
rendered_inline_node = rendered_inline_node
BaseDataDefiner = BaseDataDefiner
BaseDataDefineRole = BaseDataDefineRole
BaseDataDefineDirective = BaseDataDefineDirective
BaseDataDefineDirective = BaseDataDefineDirective
StrictDataDefineDirective = StrictDataDefineDirective

