from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable
from types import MappingProxyType

from docutils import nodes
from sphinx.util import logging
from sphinx.config import Config as SphinxConfig

from ..utils import find_first_child


logger = logging.getLogger(__name__)


def proxy_property(func: Callable[[Any], Any]) -> property:
    @wraps(func)
    def wrapped(self: Proxy) -> Any:
        return self._normalize(func(self))

    return property(wrapped)


@dataclass(frozen=True)
class Proxy:
    _obj: Any

    def __getattr__(self, name: str) -> Any:
        # Internal attr is not accessable.
        if name.startswith('_'):
            raise AttributeError(name)

        v = getattr(self._obj, name)
        if callable(v):
            # Deny callable attr for safety.
            raise AttributeError(name)

        return self._wrap(v)

    @staticmethod
    def _wrap(v: Any) -> Any:
        cls = SPECIFIC_TYPE_REGISTRY.get(type(v))
        if cls:
            return cls(v)
        for types, cls in TYPE_REGISTRY.items():
            if isinstance(v, types):
                return cls(v)
        return v

    @staticmethod
    def _normalize(val: Any) -> Any:
        """
        对显式 property 的返回值做模板安全化处理：
        - 标量原样返回；
        - 已是 ContextProxy 原样返回；
        - 注册类型自动 wrap；
        - 容器转换为不可变快照并递归处理；
        - 其他对象默认转 str。
        """
        # 标量
        if val is None or isinstance(val, (str, int, float, bool)):
            return val

        # 已包装过
        if isinstance(val, Proxy):
            return val

        # 注册类型自动 wrap
        wrapped_val = Proxy._wrap(val)
        if wrapped_val is not val:
            return wrapped_val

        # 容器
        if isinstance(val, (set, frozenset)):
            return frozenset(Proxy._normalize(x) for x in val)
        if isinstance(val, (list, tuple)):
            return tuple(Proxy._normalize(x) for x in val)
        if isinstance(val, dict):
            copied = {k: Proxy._normalize(v) for k, v in val.items()}
            return MappingProxyType(copied)

        # 其他对象：安全起见转成字符串
        return str(val)


@dataclass(frozen=True)
class Node(Proxy):
    _obj: nodes.Element

    @proxy_property
    def attrs(self) -> dict[str, str]:
        """Shortcut to :attr:`nodes.Element.attributes`."""
        return self._obj.attributes

    def __str__(self) -> str:
        return self._obj.astext()


@dataclass(frozen=True)
class NodeWithTitle(Node):
    @proxy_property
    def title(self) -> Node | None:
        return find_first_child(self._obj, nodes.Titular)  # type: ignore


@dataclass(frozen=True)
class Section(NodeWithTitle):
    _obj: nodes.section

    @proxy_property
    def sections(self) -> tuple['Section', ...]:
        sect_nodes = self._obj[0].findall(
            nodes.section, descend=False, ascend=False, siblings=True
        )
        return list(sect_nodes)


@dataclass(frozen=True)
class Document(NodeWithTitle):
    _obj: nodes.document

    def _top_section(self) -> Section:
        section = self._obj.next_node(nodes.section)
        assert section
        return Section(section)

    @proxy_property
    def sections(self) -> tuple[Section, ...]:
        return self._top_section().sections


@dataclass(frozen=True)
class Config(Proxy):
    _obj: SphinxConfig


TYPE_REGISTRY: dict[type | tuple[type, ...], type[Proxy]] = {
    nodes.Node: Node,
}

SPECIFIC_TYPE_REGISTRY: dict[type, type[Proxy]] = {
    nodes.document: Document,
    nodes.section: Section,
    SphinxConfig: Config,
}


def proxy(v: Any) -> Proxy | None:
    return Proxy._wrap(v) if v is not None else None
