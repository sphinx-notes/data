from .data import Schema, Field
from .template import Template, Phase


class Directive:
    @staticmethod
    def schema() -> Schema:
        return Schema(name=Field(), attrs=Field(), content=Field())

    @staticmethod
    def template() -> Template:
        return Template(
            debug=True,
            phase=Phase.Parsing,
            text=""".. note::

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
        return Template(
            debug=True,
            phase=Phase.Parsing,
            text="""``{{ content or 'None' }}``
:abbr:`ⁱⁿᶠᵒ (This is a default template for rendering the data your deinfed
Please create your own template using the data.tmpl directive.)`""",
        )
