"""
sphinxnotes.data.config
~~~~~~~~~~~~~~~~~~~~~~~

:copyright: Copyright 2025~2026 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import ClassVar
    from sphinx.application import Sphinx
    from sphinx.config import Config as SphinxConfig


class Config:
    """Global config of extension."""

    render_debug: ClassVar[bool]


def _config_inited(app: Sphinx, config: SphinxConfig) -> None:
    Config.render_debug = config.data_render_debug


def setup(app: Sphinx):
    app.add_config_value('data_render_debug', False, '', bool)

    app.connect('config-inited', _config_inited)
