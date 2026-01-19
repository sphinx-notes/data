from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from docutils.nodes import system_message

from ..utils import Report
from .nodes import pending_data, rendered_data


@dataclass
class Reporter:
    """A helper class for storing :cls:`Report` to data nodes."""

    node: pending_data | rendered_data

    @property
    def reports(self) -> list[Report]:
        """Use ``node += Report('xxx')`` to append a report."""
        return [x for x in self.node if isinstance(x, Report)]

    def append(self, report: Report) -> None:
        self.node += report

    def clear(self, pred: Callable[[Report], bool] | None = None) -> list[Report]:
        """Clear report children from node if pred returns True."""
        msgs = []
        for report in self.reports:
            if not pred or pred(report):
                msgs.append(report)
                self.node.remove(report)
        return msgs

    def clear_empty(self) -> None:
        self.clear(lambda x: x.empty())

    @staticmethod
    def reports_to_system_messages(reports: list[Report]) -> list[system_message]:
        return [x for x in reports]
