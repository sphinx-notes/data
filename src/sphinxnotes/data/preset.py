"""
sphinxnotes.data.preset
~~~~~~~~~~~~~~~~~~~~~~~

Preset templates and schemas.

:copyright: Copyright 2026 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from .data import Schema, Field
from .render import Template


class Directive:
    @staticmethod
    def schema() -> Schema:
        return Schema(name=Field(), attrs=Field(), content=Field())

    @staticmethod
    def template() -> Template:
        return Template(
            """.. note::

   This is a default template for rendering the data your deinfed.
   Please create your own template using the :rst:dir:`data:tmpl` directive.

:Name: ``{{ name or 'None' }}``
{% for k, v in attrs.items() %}
:{{ k }}: ``{{ v or 'None' }}``
{%- endfor %}
:content:
    ::

        {{ content or 'None' }}""",
        )


class Role:
    @staticmethod
    def schema() -> Schema:
        return Schema(name=None, attrs={}, content=Field())

    @staticmethod
    def template() -> Template:
        return Template("""``{{ content or 'None' }}``
:abbr:`ⁱⁿᶠᵒ (This is a default template for rendering the data your deinfed
Please create your own template using the data.tmpl directive.)`""")
