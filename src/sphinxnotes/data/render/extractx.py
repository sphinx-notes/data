from __future__ import annotations
from typing import TYPE_CHECKING, override
from abc import ABC, abstractmethod

from sphinx.util.docutils import SphinxDirective

from .render import HostWrapper
from .datanodes import pending_data
from ..utils import find_current_section, Report, Reporter
from ..utils.ctxproxy import proxy

if TYPE_CHECKING:
    from typing import Any, Callable, ClassVar
    from sphinx.application import Sphinx
    from .render import ParseHost, TransformHost


class GlobalExtraContxt(ABC):
    @abstractmethod
    def generate(self) -> Any: ...


class ParsePhaseExtraContext(ABC):
    @abstractmethod
    def generate(self, host: ParseHost) -> Any: ...


class TransformPhaseExtraContext(ABC):
    @abstractmethod
    def generate(self, host: TransformHost) -> Any: ...


# =======================
# Extra context registion
# =======================


class ExtraContextRegistry:
    names: set[str]
    parsing: dict[str, ParsePhaseExtraContext]
    parsed: dict[str, ParsePhaseExtraContext]
    post_transform: dict[str, TransformPhaseExtraContext]
    global_: dict[str, GlobalExtraContxt]

    def __init__(self) -> None:
        self.names = set()
        self.parsing = {}
        self.parsed = {}
        self.post_transform = {}
        self.global_ = {}

        self.add_global_context('sphinx', _SphinxExtraContext())
        self.add_parsing_phase_context('markup', _MarkupExtraContext())
        self.add_parsing_phase_context('section', _SectionExtraContext())
        self.add_parsing_phase_context('doc', _DocExtraContext())

    def _name_dedup(self, name: str) -> None:
        # TODO: allow dup
        if name in self.names:
            raise ValueError(f'Context generator {name} already exists')
        self.names.add(name)

    def add_parsing_phase_context(
        self, name: str, ctxgen: ParsePhaseExtraContext
    ) -> None:
        self._name_dedup(name)
        self.parsing['_' + name] = ctxgen

    def add_parsed_phase_context(
        self, name: str, ctxgen: ParsePhaseExtraContext
    ) -> None:
        self._name_dedup(name)
        self.parsed['_' + name] = ctxgen

    def add_post_transform_phase_context(
        self, name: str, ctxgen: TransformPhaseExtraContext
    ) -> None:
        self._name_dedup(name)
        self.post_transform['_' + name] = ctxgen

    def add_global_context(self, name: str, ctxgen: GlobalExtraContxt):
        self._name_dedup(name)
        self.global_['_' + name] = ctxgen


# ===================================
# Bulitin extra context implementions
# ===================================


class _MarkupExtraContext(ParsePhaseExtraContext):
    @override
    def generate(self, host: ParseHost) -> Any:
        isdir = isinstance(host, SphinxDirective)
        return {
            'type': 'directive' if isdir else 'role',
            'name': host.name,
            'lineno': host.lineno,
            'rawtext': host.block_text if isdir else host.rawtext,
        }


class _DocExtraContext(ParsePhaseExtraContext):
    @override
    def generate(self, host: ParseHost) -> Any:
        return proxy(HostWrapper(host).doctree)


class _SectionExtraContext(ParsePhaseExtraContext):
    @override
    def generate(self, host: ParseHost) -> Any:
        parent = HostWrapper(host).parent
        return proxy(find_current_section(parent))


class _SphinxExtraContext(GlobalExtraContxt):
    app: ClassVar[Sphinx]

    @override
    def generate(self) -> Any:
        return proxy(self.app)


# ========================
# Extra Context Management
# ========================


class ExtraContextGenerator:
    node: pending_data
    report: Report

    registry: ClassVar[ExtraContextRegistry] = ExtraContextRegistry()

    def __init__(self, node: pending_data) -> None:
        self.node = node
        self.report = Report(
            'Extra Context Generation Report',
            'ERROR',
            source=node.source,
            line=node.line,
        )
        Reporter(node).append(self.report)

    def on_anytime(self) -> None:
        for name, ctxgen in self.registry.global_.items():
            self._safegen(name, lambda: ctxgen.generate())

    def on_parsing(self, host: ParseHost) -> None:
        for name, ctxgen in self.registry.parsing.items():
            self._safegen(name, lambda: ctxgen.generate(host))

    def on_parsed(self, host: ParseHost) -> None:
        for name, ctxgen in self.registry.parsed.items():
            self._safegen(name, lambda: ctxgen.generate(host))

    def on_post_transform(self, host: TransformHost) -> None:
        for name, ctxgen in self.registry.post_transform.items():
            self._safegen(name, lambda: ctxgen.generate(host))

    def _safegen(self, name: str, gen: Callable[[], Any]):
        try:
            # ctxgen.generate can be user-defined code, exception of any kind are possible.
            self.node.extra[name] = gen()
        except Exception:
            self.report.text(f'Failed to generate extra context "{name}":')
            self.report.excption()


def setup(app: Sphinx):
    _SphinxExtraContext.app = app
