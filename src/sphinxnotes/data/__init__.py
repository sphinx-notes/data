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

if TYPE_CHECKING:
    from sphinx.application import Sphinx

logger = logging.getLogger(__name__)

def setup(app: Sphinx):
    meta.pre_setup(app)

    from . import template
    from . import render
    from . import adhoc

    template.setup(app)
    render.setup(app)
    adhoc.setup(app)

    return meta.post_setup(app)
