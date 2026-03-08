"""
Attribute-Based Access Control (ABAC) Policy Engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Evaluates access decisions based on user attributes, resource attributes,
and environmental conditions (time-of-day, IP range, etc.).

Policies are evaluated top-to-bottom; first matching policy wins.
"""

import re
from typing import Any, Dict, List, Optional, Set

from .._standards import Permission, ResourceType


class ABACCondition:
    """A single boolean predicate in an ABAC policy."""

    _OPERATORS = {
        "eq": lambda a, b: a == b,
        "ne": lambda a, b: a != b,
        "gt": lambda a, b: a > b,
        "lt": lambda a, b: a < b,
        "gte": lambda a, b: a >= b,
        "lte": lambda a, b: a <= b,
        "in": lambda a, b: a in b,
        "not_in": lambda a, b: a not in b,
        "contains": lambda a, b: b in a,
        "matches": lambda a, b: bool(re.search(b, str(a))),
    }

    def __init__(self, attribute: str, operator: str, value: Any) -> None:
        if operator not in self._OPERATORS:
            raise ValueError(f"Unknown ABAC operator: {operator}")
        self.attribute = attribute
        self.operator = operator
        self.value = value

    def evaluate(self, context: Dict[str, Any]) -> bool:
        actual = context.get(self.attribute)
        if actual is None:
            return False
        return self._OPERATORS[self.operator](actual, self.value)


class ABACPolicy:
    """An ABAC policy: a set of conditions joined by AND/OR with an effect."""

    def __init__(
        self,
        policy_id: str,
        name: str,
        *,
        effect: str = "allow",
        combine: str = "all",
        priority: int = 0,
    ) -> None:
        if effect not in ("allow", "deny"):
            raise ValueError(f"effect must be 'allow' or 'deny', got {effect!r}")
        if combine not in ("all", "any"):
            raise ValueError(f"combine must be 'all' or 'any', got {combine!r}")
        self.policy_id = policy_id
        self.name = name
        self.effect = effect
        self.combine = combine
        self.priority = priority
        self.conditions: List[ABACCondition] = []
        self.target_permissions: Set[Permission] = set()
        self.target_resource_types: Set[ResourceType] = set()

    def add_condition(
        self, attribute: str, operator: str, value: Any
    ) -> "ABACPolicy":
        self.conditions.append(ABACCondition(attribute, operator, value))
        return self  # allow chaining

    def evaluate(self, context: Dict[str, Any]) -> Optional[bool]:
        """Return ``True`` (allow), ``False`` (deny), or ``None`` (no match)."""
        if not self.conditions:
            return None
        results = [c.evaluate(context) for c in self.conditions]
        match = all(results) if self.combine == "all" else any(results)
        if match:
            return self.effect == "allow"
        return None


class ABACEngine:
    """Evaluates an ordered list of ABAC policies."""

    def __init__(self) -> None:
        self.policies: List[ABACPolicy] = []

    def add_policy(self, policy: ABACPolicy) -> None:
        self.policies.append(policy)
        self.policies.sort(key=lambda p: p.priority, reverse=True)

    def remove_policy(self, policy_id: str) -> None:
        self.policies = [
            p for p in self.policies if p.policy_id != policy_id
        ]

    def evaluate(self, context: Dict[str, Any]) -> Optional[bool]:
        """First-match evaluation.  ``None`` means no policy matched."""
        for policy in self.policies:
            result = policy.evaluate(context)
            if result is not None:
                return result
        return None
