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
        return Registry.strifys[type(v)](v)


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
    raise ValueError(f'no argument is allowed; "{v}" supplied')


def _str_conv(v: str) -> str:
    try:
        vv = literal_eval(v)
    except (ValueError, SyntaxError):
        return v
    return vv if isinstance(vv, str) else v


class Registry:
    """Stores supported element types and element forms (containers)."""

    etypes: dict[str, type] = {}

    ctypes: set[type] = {list, tuple, set}

    convs: dict[type, Callable[[str], PlainValue]] = {}

    strifys: dict[type, Callable[[PlainValue], str]] = {}

    forms: dict[str, Form] = {}

    flags: dict[str, Flag] = {}

    byopts: dict[str, ByOption] = {}

    _sep_by_option: ByOption

    @classmethod
    def add_type(
        cls,
        name: str,
        etype: type,
        conv: Callable[[str], PlainValue],
        strify: Callable[[PlainValue], str],
        aliases: list[str] = [],
    ) -> None:
        cls.etypes[name] = etype
        cls.convs[etype] = conv
        cls.strifys[etype] = strify

        for alias in aliases:
            cls.etypes[alias] = etype

    @classmethod
    def add_form(
        cls, name: str, ctype: type, sep: str, aliases: list[str] = []
    ) -> None:
        if ctype not in cls.ctypes:
            raise ValueError(f'unsupported type: "{ctype}". available: {cls.ctypes}')

        form = Form(ctype, sep)

        cls.forms[name] = form
        for alias in aliases:
            cls.forms[alias] = form

    @classmethod
    def add_flag(
        cls, name: str, default: bool = False, aliases: list[str] = []
    ) -> None:
        flag = Flag(name, default)

        cls.flags[flag.name] = flag
        for alias in aliases:
            cls.flags[alias] = flag

    @classmethod
    def add_by_option(
        cls,
        name: str,
        etype: type,
        default: Value = None,
        store: ByOptionStore = 'assign',
        aliases: list[str] = [],
    ) -> None:
        opt = ByOption(name, etype, default, store)

        cls.byopts[opt.name] = opt
        for alias in aliases:
            cls.byopts[alias] = opt

    @classmethod
    def setup(cls) -> None:
        cls.add_type('bool', bool, conv=_bool_conv, strify=str, aliases=['flag'])
        cls.add_type('int', int, conv=int, strify=str, aliases=['integer'])
        cls.add_type('float', float, conv=float, strify=str, aliases=['number', 'num'])
        cls.add_type('str', str, conv=_str_conv, strify=str, aliases=['string'])

        cls.add_form('list', list, ',')
        cls.add_form('lines', list, '\n')
        cls.add_form('words', list, ' ')
        cls.add_form('set', set, ' ')

        cls.add_flag('required', False, aliases=['require', 'req'])

        cls.add_by_option('sep', str, aliases=['separate'])
        # NOTE: the "sep" by-option is a special builtin flag, extract it for
        # later usage.
        cls._sep_by_option = cls.byopts['sep']

        # from pprint import pprint
        # pprint(cls.__dict__)


Registry.setup()

# ======================
# Data, Field and Schema
# ======================


@dataclass
class RawData:
    name: str | None
    attrs: dict[str, str]
    content: str | None


@dataclass
class Data:
    name: Value
    attrs: dict[str, Value]
    content: Value

    def ascontext(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Field:
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
        for flag in Registry.flags.values():
            if flag.name not in self.flags:
                self.flags[flag.name] = flag.default
        for opt in Registry.byopts.values():
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
                raise ValueError('argument required but none supplied')
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
            conv = Registry.convs[self.etype]

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
            raise ValueError(f"failed to parse '{rawval}' as {self.etype}: {e}") from e

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

            if etype not in Registry.etypes:
                raise ValueError(
                    f'unsupported type: "{etype}". '
                    f'available: {list(Registry.etypes.keys())}'
                )
            if form not in Registry.forms:
                raise ValueError(
                    f'unsupported form: "{form}". '
                    f'available: {list(Registry.forms.keys())}'
                )

            self.field.etype = Registry.etypes[etype]
            self.field.ctype = Registry.forms[form].ctype
            self.field.flags[Registry._sep_by_option.name] = Registry.forms[form].sep
            return

        # Match: Type only (e.g., "int")
        if lower_mod in Registry.etypes:
            self.field.etype = Registry.etypes[lower_mod]
            return

        # Match: by-option, "XXX by XXX" (e.g., "sep by '|'")
        if match := re.match(r'^([a-zA-Z_]+)\s+by\s+(.+)$', clean_mod, re.IGNORECASE):
            optname, rawval = match.groups()

            if optname not in Registry.byopts:
                raise ValueError(
                    f'unsupported by-option: "{optname}" by. '
                    f'available: {list(Registry.byopts.keys())}'
                )

            flags = self.field.flags
            opt = Registry.byopts[optname]
            val = Registry.convs[opt.etype](rawval)

            if opt.store == 'assign':
                flags[opt.name] = val
            elif opt.store == 'append':
                vals = flags[opt.name]
                assert isinstance(vals, list)
                vals.append(val)
            else:
                raise self.by_option_store_value_error(opt)

            # Deal with special by option.
            if opt == Registry._sep_by_option:
                # ctype default to list if 'sep by' is used without a 'xxx of xxx'.
                if self.field.ctype is None:
                    self.field.ctype = list

            return

        # Match: flags.
        if lower_mod in Registry.flags:
            opt = Registry.flags[lower_mod]
            self.field.flags[opt.name] = not opt.default
            return

        raise ValueError(f"unknown modifier: '{mod}'")

    @staticmethod
    def by_option_store_value_error(opt: ByOption) -> ValueError:
        raise ValueError(
            f'unsupported by-option store: "{opt.store}". '
            f'available: {ByOptionStore}'  # FIXME:
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
                f'parsing {field[0]}: no argument is allowed; "{rawval}" supplied'
            )

        try:
            assert field[1] is not None
            return field[1].parse(rawval)
        except Exception as e:
            raise ValueError(f'parsing {field[0]}: {e}')

    def parse(self, data: RawData) -> Data:
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
                raise ValueError(f'unknown attr: "{key}"')

        if data.content:
            content = self._parse_single(('content', self.content), data.content)
        else:
            content = None

        return Data(name, attrs, content)

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

    def items(self, data: Data) -> Generator[tuple[str, Field, Value]]:
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
