"""
sphinxnotes.dataview
~~~~~~~~~~~~~~~~~~~~

:copyright: Copyright 2025 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import cast, override

from docutils import nodes
from docutils.parsers.rst import directives
from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective
from sphinx.application import Sphinx

from . import meta
from .data import Field, Schema
from .template import Template, Phase
from .render import BaseDataDefineDirective, BaseDataDefineRole
from .utils.freestyle import FreeStyleDirective, FreeStyleOptionSpec
from . import preset

logger = logging.getLogger(__name__)

TEMPLATE_KEY = 'sphinxnotes:template'
SCHEMA_KEY = 'sphinxnotes:data'


class TemplateDirective(SphinxDirective):
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


class SchemaDirective(FreeStyleDirective):
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


class FreeDataRole(BaseDataDefineRole):
    @override
    def current_template(self) -> Template:
        tmpl = self.env.temp_data.get(TEMPLATE_KEY, preset.Role.template())
        return cast(Template, tmpl)

    @override
    def current_schema(self) -> Schema:
        schema = self.env.temp_data.get(SCHEMA_KEY, preset.Role.schema())
        return cast(Schema, schema)


class FreeDataDirective(BaseDataDefineDirective, FreeStyleDirective):
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


# class AutoFreeDataDirective(FreeDataDirective):
#     @override
#     def process_pending_node(self, n: pending_node) -> None:
#         n.name_external = n.content_external = True
#
#     @override
#     def current_template(self) -> Template:
#         tmpl = super().current_template()
#         tmpl.debug = True
#         tmpl.phase = Phase.Parsed
#         return tmpl


def setup(app: Sphinx):
    meta.pre_setup(app)

    from . import template
    from . import render

    template.setup(app)
    render.setup(app)

    app.add_config_value('data_template_debug', True, types=bool, rebuild='')

    app.add_directive('data.tmpl', TemplateDirective)
    app.add_directive('data.template', TemplateDirective)
    app.add_directive('data.schema', SchemaDirective)
    app.add_directive('data', FreeDataDirective)

    app.add_role('data', FreeDataRole())

    # app.add_directive('data.dir', TemplateDirective, False)
    # app.add_directive('data.role', TemplateDirective, False)

    return meta.post_setup(app)
