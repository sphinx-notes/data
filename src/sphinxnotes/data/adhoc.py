"""
sphinxnotes.data.adhoc
~~~~~~~~~~~~~~~~~~~~~~

This extension allow user define, validate, and render data in a document
on the fly

(Yes, Use markup language (rst/md) entirely, instead of Python).

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.

"""

from __future__ import annotations
from typing import TYPE_CHECKING, cast, override

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util.docutils import SphinxDirective

from .data import Field, Schema
from .template import Template, Phase
from .render import BaseDataDefineDirective
from .utils.freestyle import FreeStyleDirective, FreeStyleOptionSpec
from . import preset

if TYPE_CHECKING:
    from sphinx.application import Sphinx

# Keys of env.temp_data.
TEMPLATE_KEY = 'sphinxnotes-data:template'
SCHEMA_KEY = 'sphinxnotes-data:schema'


class TemplateDefineDirective(SphinxDirective):
    option_spec = {
        'on': Phase.option_spec,
        'debug': directives.flag,
    }
    has_content = True

    def run(self) -> list[nodes.Node]:
        self.env.temp_data[TEMPLATE_KEY] = Template(
            text='\n'.join(self.content),
            phase=self.options.get('on', Phase.default()),
            debug='debug' in self.options,
        )

        return []


class SchemaDefineDirective(FreeStyleDirective):
    optional_arguments = 1
    option_spec = FreeStyleOptionSpec()
    has_content = True

    def run(self) -> list[nodes.Node]:
        name = Field.from_dsl(self.arguments[0]) if self.arguments else None
        attrs = {}
        for k, v in self.options.items():
            attrs[k] = Field.from_dsl(v)
        content = Field.from_dsl(self.content[0]) if self.content else None

        self.env.temp_data[SCHEMA_KEY] = Schema(name, attrs, content)

        return []


class FreeDataDefineDirective(BaseDataDefineDirective, FreeStyleDirective):
    optional_arguments = 1
    has_content = True

    @override
    def current_template(self) -> Template:
        tmpl = self.env.temp_data.get(TEMPLATE_KEY, preset.Directive.template())
        return cast(Template, tmpl)

    @override
    def current_schema(self) -> Schema:
        schema = self.env.temp_data.get(SCHEMA_KEY, preset.Directive.schema())
        return cast(Schema, schema)


def setup(app: Sphinx):
    app.add_directive('template', TemplateDefineDirective)
    app.add_directive('schema', SchemaDefineDirective)
    app.add_directive('data', FreeDataDefineDirective)
