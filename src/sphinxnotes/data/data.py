from __future__ import annotations
from typing import TYPE_CHECKING
import re
from dataclasses import dataclass, asdict, field as dataclass_field
from ast import literal_eval

if TYPE_CHECKING:
    from typing import Any, Callable, Generator, Self, Literal


#########################################
# Basic classes: Value, Form, Flag, ... #
#########################################

type PlainValue = bool | int | float | str
type Value = None | PlainValue | list[PlainValue]


@dataclass
class ValueWrapper:
    v: Value

    def as_plain(self) -> PlainValue | None:
        if self.v is None:
            return None
        if isinstance(self.v, list):
            if len(self.v) == 0:
                return None
            return self.v[0]
        return self.v

    def as_str(self) -> str | None:
        return str(self.as_plain())

    def as_list(self) -> list[PlainValue]:
        if self.v is None:
            return []
        elif isinstance(self.v, list):
            return [x for x in self.v]
        else:
            return [self.v]

    def as_str_list(self) -> list[str]:
        if self.v is None:
            return []
        elif isinstance(self.v, list):
            return [str(x) for x in self.v]
        else:
            return [str(self.v)]


@dataclass(frozen=True)
class Form:
    """Defines how to split the string and the container type."""

    ctype: type
    sep: str


@dataclass(frozen=True)
class Flag:
    name: str


@dataclass(frozen=True)
class BoolFlag(Flag):
    default: bool = False


type FlagStore = Literal['assign', 'append']


@dataclass(frozen=True)
class OperFlag(Flag):
    etype: type = str
    default: Value = None
    store: FlagStore = 'assign'


############
# Registry #
############


class Registry:
    """Stores supported element types and element forms (containers)."""

    etypes: dict[str, type] = {
        'bool': bool,
        'flag': bool,
        'int': int,
        'integer': int,
        'float': float,
        'number': float,
        'num': float,
        'str': str,
        'string': str,
    }

    """Internal type converters."""

    @staticmethod
    def _bool_conv(v: str | None) -> bool:
        v = v.lower().strip() if v is not None else None
        if v in ('true', 'yes', '1', 'on', 'y', ''):
            return True
        if v in ('false', 'no', '0', 'off', 'n', None):
            return False
        # Same to :meth:`directives.flag`.
        raise ValueError(f'no argument is allowed; "{v}" supplied')

    @staticmethod
    def _str_conv(v: str) -> str:
        try:
            vv = literal_eval(v)
        except (ValueError, SyntaxError):
            return v
        return vv if isinstance(vv, str) else v

    convs: dict[type, Callable[[str], Any]] = {
        bool: _bool_conv,
        int: int,
        float: float,
        str: _str_conv,
    }

    forms: dict[str, Form] = {
        'list': Form(ctype=list, sep=','),
        'lines': Form(ctype=list, sep='\n'),
        'words': Form(ctype=list, sep=' '),
    }

    """Builtin flags."""

    _required_flag = BoolFlag('required')
    _sep_flag = OperFlag('sep', etype=str)

    flags: dict[str, BoolFlag] = {
        'required': _required_flag,
        'require': _required_flag,
        'req': _required_flag,
    }

    byflags: dict[str, OperFlag] = {
        'separate': _sep_flag,
        'sep': _sep_flag,
    }


##########################
# Data, Field and Schema #
##########################


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

    def title(self) -> str | None:
        return ValueWrapper(self.name).as_str()


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
        for flag in Registry.byflags.values():
            if flag.name not in self.flags:
                self.flags[flag.name] = flag.default

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
                return Registry._bool_conv(rawval)
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
            raise ValueError(f"failed to parse '{rawval}' as {self.etype}: {e}")

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
            self.field.flags[Registry._sep_flag.name] = Registry.forms[form].sep
            return

        # Match: Type only (e.g., "int")
        if lower_mod in Registry.etypes:
            self.field.etype = Registry.etypes[lower_mod]
            return

        # Match: XXX by XXX (e.g., "sep by '|'")
        if match := re.match(r'^([a-zA-Z_]+)\s+by\s+(.+)$', clean_mod, re.IGNORECASE):
            flagname, rawval = match.groups()

            if flagname not in Registry.byflags:
                raise ValueError(
                    f'unsupported flag: "{flagname}" by. '
                    f'available: {list(Registry.byflags.keys())}'
                )

            flags = self.field.flags
            flag = Registry.byflags[flagname]
            val = Registry.convs[flag.etype](rawval)

            if flag.store == 'assign':
                flags[flag.name] = val
            elif flag.store == 'append':
                if flags[flag.name] is None:
                    flags[flag.name] = []
                vals = flags[flag.name]
                assert isinstance(vals, list)
                vals.append(val)
            else:
                raise ValueError(
                    f'unsupported flag store: "{flag.store}". available: {FlagStore}'
                )

            # Deal with builtin flags.
            if flag == Registry._sep_flag:
                # ctype default to list if 'sep by' is used without a 'xxx of xxx'.
                if self.field.ctype is None:
                    self.field.ctype = list

            return

        # Match: bool flags.
        if lower_mod in Registry.flags:
            flag = Registry.flags[lower_mod]
            self.field.flags[flag.name] = not flag.default
            return

        raise ValueError(f"unknown modifier: '{mod}'")


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
