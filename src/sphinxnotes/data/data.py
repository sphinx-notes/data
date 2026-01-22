"""
sphinxnotes.data.data
~~~~~~~~~~~~~~~~~~~~~

Core type definitions.

:copyright: Copyright 2025~2026 by the Shengyu Zhang.
:license: BSD, see LICENSE for details.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
import re
from dataclasses import dataclass, asdict, field as dataclass_field
from ast import literal_eval

from .utils import Unpicklable

if TYPE_CHECKING:
    from typing import Any, Callable, Generator, Self, Literal

# ===================================
# Basic types: Value, Form, Flag, ...
# ===================================

type PlainValue = bool | int | float | str | object
type Value = None | PlainValue | list[PlainValue]


@dataclass
class ValueWrapper:
    v: Value

    # TODO: __post_init__ to assert type

    def as_plain(self) -> PlainValue | None:
        if self.v is None:
            return None
        if isinstance(self.v, list):
            return self.v[0] if len(self.v) else None
        return self.v

    def as_list(self) -> list[PlainValue]:
        if self.v is None:
            return []
        elif isinstance(self.v, list):
            return [x for x in self.v]
        else:
            return [self.v]

    def as_str(self) -> str | None:
        v = self.as_plain()
        return self._strify(v) if v is not None else None

    def as_str_list(self) -> list[str]:
        return [self._strify(x) for x in self.as_list()]

    @staticmethod
    def _strify(v: PlainValue) -> str:
        return REGISTRY.strifys[type(v)](v)


@dataclass(frozen=True)
class Form:
    """Defines how to split the string and the container type."""

    ctype: type
    sep: str


@dataclass(frozen=True)
class Flag:
    name: str
    default: bool


type ByOptionStore = Literal['assign', 'append']


@dataclass(frozen=True)
class ByOption:
    name: str
    etype: type
    default: Value
    store: ByOptionStore


# ========
# Registry
# ========


def _bool_conv(v: str | None) -> bool:
    v = v.lower().strip() if v is not None else None
    if v in ('true', 'yes', '1', 'on', 'y', ''):
        return True
    if v in ('false', 'no', '0', 'off', 'n', None):
        return False
    # Same to :meth:`directives.flag`.
    raise ValueError(f'No argument is allowed; "{v}" supplied')


def _str_conv(v: str) -> str:
    try:
        vv = literal_eval(v)
    except (ValueError, SyntaxError):
        return v
    return vv if isinstance(vv, str) else v


class Registry:
    """Stores supported element types and element forms (containers)."""

    etypes: dict[str, type]
    ctypes: set[type] = {list, tuple, set}
    convs: dict[type, Callable[[str], PlainValue]]
    strifys: dict[type, Callable[[PlainValue], str]]
    forms: dict[str, Form]
    flags: dict[str, Flag]
    byopts: dict[str, ByOption]

    _sep_by_option: ByOption

    def __init__(self) -> None:
        self.etypes = {}
        self.convs = {}
        self.strifys = {}
        self.forms = {}
        self.flags = {}
        self.byopts = {}

        # Add builtin types.
        self.add_type('bool', bool, _bool_conv, str, aliases=['flag'])
        self.add_type('int', int, int, strify=str, aliases=['integer'])
        self.add_type('float', float, float, str, aliases=['number', 'num'])
        self.add_type('str', str, _str_conv, str, aliases=['string'])

        # Add builtin forms.
        self.add_form('list', list, ',')
        self.add_form('lines', list, '\n')
        self.add_form('words', list, ' ')
        self.add_form('set', set, ' ')

        # Add builtin flags.
        self.add_flag('required', False, aliases=['require', 'req'])

        # Add builtin by-option.
        self.add_by_option('sep', str, aliases=['separate'])
        # NOTE: the "sep" by-option is a special builtin flag, extract it for
        # later usage.
        self._sep_by_option = self.byopts['sep']

        # from pprint import pprint
        # pprint(cls.__dict__)

    def add_type(
        self,
        name: str,
        etype: type,
        conv: Callable[[str], PlainValue],
        strify: Callable[[PlainValue], str],
        aliases: list[str] = [],
    ) -> None:
        self.etypes[name] = etype
        self.convs[etype] = conv
        self.strifys[etype] = strify

        for alias in aliases:
            self.etypes[alias] = etype

    def add_form(
        self, name: str, ctype: type, sep: str, aliases: list[str] = []
    ) -> None:
        if ctype not in self.ctypes:
            raise ValueError(f'Unsupported type: "{ctype}". Available: {self.ctypes}')

        form = Form(ctype, sep)

        self.forms[name] = form
        for alias in aliases:
            self.forms[alias] = form

    def add_flag(
        self, name: str, default: bool = False, aliases: list[str] = []
    ) -> None:
        flag = Flag(name, default)

        self.flags[flag.name] = flag
        for alias in aliases:
            self.flags[alias] = flag

    def add_by_option(
        self,
        name: str,
        etype: type,
        default: Value = None,
        store: ByOptionStore = 'assign',
        aliases: list[str] = [],
    ) -> None:
        opt = ByOption(name, etype, default, store)

        self.byopts[opt.name] = opt
        for alias in aliases:
            self.byopts[alias] = opt


REGISTRY = Registry()

# ======================
# Data, Field and Schema
# ======================


@dataclass
class RawData:
    name: str | None
    attrs: dict[str, str]
    content: str | None


@dataclass
class PendingData(Unpicklable):
    raw: RawData
    schema: Schema

    def parse(self) -> ParsedData:
        return self.schema.parse(self.raw)


@dataclass
class ParsedData:
    name: Value
    attrs: dict[str, Value]
    content: Value

    def asdict(self) -> dict[str, Any]:
        """
        Convert Data to a dict for usage of Jinja2 context.

        ``self.attrs`` will be automaticlly lifted to top-level context when
        there is no key conflicts. For example:

        - You can access ``Data.attrs['color']`` by "{{ color }}"" instead
        of "{{ attrs.color }}".
        - You can NOT access ``Data.attrs['name']`` by "{{ name }}" cause
        the variable name is taken by ``Data.name``.
        """
        ctx = asdict(self)
        for k, v in self.attrs.items():
            if k not in ctx:
                ctx[k] = v
        return ctx


@dataclass
class Field(Unpicklable):
    #: Type of element.
    etype: type = str
    #: Type of container (if the field holds multiple values).
    ctype: type | None = None
    #: Flags of field.
    flags: dict[str, Value] = dataclass_field(default_factory=dict)

    # Type hints for builtin flags.
    if TYPE_CHECKING:
        required: bool = False
        sep: str | None = None

    @classmethod
    def from_dsl(cls, dsl: str) -> Self:
        self = cls()
        DSLParser(self).parse(dsl)
        return self

    def __post_init__(self) -> None:
        # Init flags and by flags.
        for flag in REGISTRY.flags.values():
            if flag.name not in self.flags:
                self.flags[flag.name] = flag.default
        for opt in REGISTRY.byopts.values():
            if opt.name in self.flags:
                continue
            if opt.store == 'assign':
                self.flags[opt.name] = opt.default
            elif opt.store == 'append':
                self.flags[opt.name] = lst = []
                if opt.default is not None:
                    lst.append(opt.default)
            else:
                raise DSLParser.by_option_store_value_error(opt)

    def parse(self, rawval: str | None) -> Value:
        """
        Parses the raw input string into the target Value.
        When a None is passed, which means the field is not supplied.
        """
        if rawval is None:
            if self.required:
                # Same to :meth:`directives.unchanged_required`.
                raise ValueError('Argument required but none supplied')
            if self.ctype:
                # Return a empty container when a None value is optional.
                return self.ctype()
            if self.etype is bool:
                # Special case: A single bool field is valid even when
                # value is not supplied.
                return _bool_conv(rawval)
            return None

        # Strip whitespace. TODO: supported unchanged?
        rawval = rawval.strip()

        try:
            conv = REGISTRY.convs[self.etype]

            if self.ctype is None:
                # Parse as scalar
                return conv(rawval)

            # Parse as container
            if self.sep == ' ':
                items = rawval.split()  # split by arbitrary whitespace
            elif self.sep == '':
                items = list(rawval)  # split by char
            else:
                items = rawval.split(self.sep)

            elems = [conv(x.strip()) for x in items if x.strip() != '']

            return self.ctype(elems)
        except ValueError as e:
            raise ValueError(f"Failed to parse '{rawval}' as {self.etype}: {e}") from e

    def __getattr__(self, name: str) -> Value:
        if name in self.flags:
            return self.flags[name]
        raise AttributeError(name)


@dataclass
class DSLParser:
    field: Field

    def parse(self, dsl: str) -> None:
        """Parses the DSL string into a Field object."""
        # Initialize form as None, implied scalar unless modifiers change it.
        for mod in self._split_modifiers(dsl):
            if mod.strip():
                self._apply_modifier(mod.strip())

    def _split_modifiers(self, text: str) -> list[str]:
        """Splits the DSL string by comma, ignoring commas inside quotes."""
        parts, current, quote_char = [], [], None

        for ch in text:
            if quote_char:
                current.append(ch)
                if ch == quote_char:
                    quote_char = None
            else:
                if ch in ('"', "'"):
                    quote_char = ch
                    current.append(ch)
                elif ch == ',':
                    parts.append(''.join(current))
                    current = []
                else:
                    current.append(ch)

        if current:
            parts.append(''.join(current))

        return parts

    def _apply_modifier(self, mod: str):
        clean_mod = mod.strip()
        lower_mod = clean_mod.lower()

        # Match: XXX of XXX (e.g., "list of int")
        if match := re.match(r'^([a-zA-Z_]+)\s+of\s+([a-zA-Z_]+)$', lower_mod):
            form, etype = match.groups()

            if etype not in REGISTRY.etypes:
                raise ValueError(
                    f'Unsupported type: "{etype}". '
                    f'Available: {list(REGISTRY.etypes.keys())}'
                )
            if form not in REGISTRY.forms:
                raise ValueError(
                    f'Unsupported form: "{form}". '
                    f'Available: {list(REGISTRY.forms.keys())}'
                )

            self.field.etype = REGISTRY.etypes[etype]
            self.field.ctype = REGISTRY.forms[form].ctype
            self.field.flags[REGISTRY._sep_by_option.name] = REGISTRY.forms[form].sep
            return

        # Match: Type only (e.g., "int")
        if lower_mod in REGISTRY.etypes:
            self.field.etype = REGISTRY.etypes[lower_mod]
            return

        # Match: by-option, "XXX by XXX" (e.g., "sep by '|'")
        if match := re.match(r'^([a-zA-Z_]+)\s+by\s+(.+)$', clean_mod, re.IGNORECASE):
            optname, rawval = match.groups()

            if optname not in REGISTRY.byopts:
                raise ValueError(
                    f'Unsupported by-option: "{optname}" by. '
                    f'Available: {list(REGISTRY.byopts.keys())}'
                )

            flags = self.field.flags
            opt = REGISTRY.byopts[optname]
            val = REGISTRY.convs[opt.etype](rawval)

            if opt.store == 'assign':
                flags[opt.name] = val
            elif opt.store == 'append':
                vals = flags[opt.name]
                assert isinstance(vals, list)
                vals.append(val)
            else:
                raise self.by_option_store_value_error(opt)

            # Deal with special by option.
            if opt == REGISTRY._sep_by_option:
                # ctype default to list if 'sep by' is used without a 'xxx of xxx'.
                if self.field.ctype is None:
                    self.field.ctype = list

            return

        # Match: flags.
        if lower_mod in REGISTRY.flags:
            opt = REGISTRY.flags[lower_mod]
            self.field.flags[opt.name] = not opt.default
            return

        raise ValueError(f"Unknown modifier: '{mod}'")

    @staticmethod
    def by_option_store_value_error(opt: ByOption) -> ValueError:
        raise ValueError(
            f'Unsupported by-option store: "{opt.store}". '
            f'Available: {ByOptionStore}'  # FIXME:
        )


@dataclass(frozen=True)
class Schema(object):
    name: Field | None
    attrs: dict[str, Field] | Field
    content: Field | None

    @classmethod
    def from_dsl(
        cls,
        name: str | None = None,
        attrs: dict[str, str] = {},
        content: str | None = None,
    ) -> Self:
        name_field = Field.from_dsl(name) if name else None
        attrs_field = {k: Field.from_dsl(v) for k, v in attrs.items()}
        cont_field = Field.from_dsl(content) if content else None

        return cls(name_field, attrs_field, cont_field)

    def _parse_single(
        self, field: tuple[str, Field | None], rawval: str | None
    ) -> Value:
        if field[1] is None and rawval is not None:
            raise ValueError(
                f'Parsing {field[0]}: no argument is allowed; "{rawval}" supplied'
            )

        try:
            assert field[1] is not None
            return field[1].parse(rawval)
        except Exception as e:
            raise ValueError(f'Parsing {field[0]}: {e}')

    def parse(self, data: RawData) -> ParsedData:
        if data.name:
            name = self._parse_single(('name', self.name), data.name)
        else:
            name = None

        attrs = {}
        if isinstance(self.attrs, Field):
            for key, rawval in data.attrs.items():
                attrs[key] = self._parse_single(('attrs.' + key, self.attrs), rawval)
        else:
            rawattrs = data.attrs.copy()
            for key, field in self.attrs.items():
                if rawval := rawattrs.pop(key, None):
                    attrs[key] = self._parse_single(('attrs.' + key, field), rawval)
            for key, rawval in rawattrs.items():
                raise ValueError(f'Unknown attr: "{key}"')

        if data.content:
            content = self._parse_single(('content', self.content), data.content)
        else:
            content = None

        return ParsedData(name, attrs, content)

    def fields(self) -> Generator[tuple[str, Field]]:
        if self.name:
            yield 'name', self.name

        if isinstance(self.attrs, Field):
            yield 'attrs', self.attrs
        else:
            for name, field in self.attrs.items():
                yield name, field

        if self.content:
            yield 'content', self.content

    def items(self, data: ParsedData) -> Generator[tuple[str, Field, Value]]:
        if self.name:
            yield 'name', self.name, data.name

        if isinstance(self.attrs, Field):
            for name, val in data.attrs:
                yield name, self.attrs, val
        else:
            for name, field in self.attrs.items():
                yield name, field, data.attrs.get(name)

        if self.content:
            yield 'content', self.content, data.content
