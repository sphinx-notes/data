import re
from typing import Callable, Any

from docutils import nodes
from docutils.utils import assemble_option_dict
from docutils.parsers.rst import directives
from docutils.parsers.rst.states import Body

from sphinx.util import logging
from sphinx.util.docutils import SphinxDirective

from ..utils import parse_text_to_nodes

logger = logging.getLogger(__name__)


class FreeStyleOptionSpec(dict):
    """
    An option_spec that accepts any key and always return the same conversion
    function.
    """

    def __init__(self, conv: Callable[[str], Any] = directives.unchanged):
        self.conv = conv

    def __getitem__(self, _):
        return self.conv


class FreeStyleDirective(SphinxDirective):
    """
    TODO:
    """

    final_argument_whitespace = True
    option_spec = FreeStyleOptionSpec()

    _arguments: list[str]
    _options: dict[str, str]

    @property
    def arguments(self) -> list[str]:
        return self._arguments

    @arguments.setter
    def arguments(self, value: list[str]) -> None:  # type: ignore
        if len(value) == 0:
            self._arguments, self._options = [], {}
            return

        last_arg_and_opts = value.pop()
        self._arguments = value
        last_arg, self._options = self._parse_options(last_arg_and_opts)
        self._arguments.append(last_arg)

    @property
    def options(self) -> dict[str, str]:
        return self._options

    @options.setter
    def options(self, _: dict[str, str]) -> None: ...  # type: ignore

    def _parse_options(self, args_and_opts: str) -> tuple[str, dict[str, str]]:
        """Returns (last argument, parsed options)."""
        arg_block = args_and_opts.split('\n')
        opt_block = None

        # Extract options from arguments.
        # See also :meth:`docutils.parsers.rst.Body::parse_directive_options`.
        for i, line in enumerate(arg_block):
            if re.match(Body.patterns['field_marker'], line):
                opt_block = arg_block[i:]
                arg_block = arg_block[:i]
                break

        # Parse options raw text to dict[str, str].
        options = {}
        if opt_block:
            option_list = self._parse_field_list('\n'.join(opt_block))
            options = assemble_option_dict(option_list, self.option_spec)

        return '\n'.join(arg_block), options

    @staticmethod
    def _parse_field_list(text: str) -> list[tuple[str, str]]:
        field_lists = []
        for node in parse_text_to_nodes(text):
            for field_list in node.findall(nodes.field_list):
                for field in field_list:
                    name = field.children[0].astext()
                    value = field.children[1].astext()
                    field_lists.append((name, value))
        return field_lists
