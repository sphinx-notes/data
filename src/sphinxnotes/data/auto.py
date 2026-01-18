"""
sphinxnotes.data.derive
~~~~~~~~~~~~~~~~~~~~~~~

Module for rendering data to doctree nodes.

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING, override

from .data import RawData, PendingData
from .template import Template, Phase
from .render import BaseDataDefineDirective, pending_node
from .utils import find_titular_node_upward

if TYPE_CHECKING:
    ...


class AutoDataDefineDirective(BaseDataDefineDirective):
    external_name_template = Template(
        phase=Phase.Parsed,
        debug=True,
        text="""wow *{{ name }}*
.. note:: hi here :""",
    )

    @override
    def current_raw_data(self) -> RawData:
        data = super().current_raw_data()
        if data.name is None:
            return data

        if title := find_titular_node_upward(self.state.parent):
            data.name = title.astext()
            pending_data = PendingData(data, self.current_schema())
            pending_title = pending_node(pending_data, self.external_name_template)
            pending_title.seamless = True
            pending_title.inline = True
            title.clear()
            title += pending_title
        return data
