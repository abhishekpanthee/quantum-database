"""
Row-Level Security & Column Masking
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Fine-grained data-access controls applied *after* permission checks.

RLS policies filter which rows a user can see.  Column masks redact
sensitive columns before data is returned.
"""

from typing import Any, Callable, Dict, List, Optional, Set

from .models import User


class RLSPolicy:
    """Predicate that filters rows visible to a user or set of roles.

    Policy types:

    * **permissive** — at least one permissive policy must pass for a row
      to be visible.  If no permissive policies exist, all rows are visible.
    * **restrictive** — *all* restrictive policies must pass.
    """

    def __init__(
        self,
        policy_id: str,
        name: str,
        *,
        resource_id: str,
        predicate: Callable[[Dict[str, Any], User], bool],
        applies_to: Optional[Set[str]] = None,
        policy_type: str = "permissive",
    ) -> None:
        if policy_type not in ("permissive", "restrictive"):
            raise ValueError(
                f"policy_type must be 'permissive' or 'restrictive'"
            )
        self.policy_id = policy_id
        self.name = name
        self.resource_id = resource_id
        self.predicate = predicate
        self.applies_to = applies_to  # role IDs; None → all
        self.policy_type = policy_type

    def evaluate(self, row: Dict[str, Any], user: User) -> bool:
        """Return ``True`` if the *row* is visible to *user*."""
        if self.applies_to is not None:
            if not self.applies_to.intersection(user.roles):
                # Policy doesn't target this user's roles
                return self.policy_type == "permissive"
        return self.predicate(row, user)


class ColumnMask:
    """Redacts a column value before it is returned to the user.

    The default mask keeps the first and last character and replaces
    everything in between with ``*``.  Users whose roles overlap with
    ``exempt_roles`` see the raw value.
    """

    def __init__(
        self,
        column_name: str,
        *,
        mask_fn: Optional[Callable[[Any, User], Any]] = None,
        exempt_roles: Optional[Set[str]] = None,
    ) -> None:
        self.column_name = column_name
        self.mask_fn = mask_fn or self._default_mask
        self.exempt_roles = exempt_roles or set()

    @staticmethod
    def _default_mask(value: Any, user: User) -> Any:
        if isinstance(value, str):
            if len(value) <= 2:
                return "***"
            return value[0] + "*" * (len(value) - 2) + value[-1]
        return "***"

    def apply(self, value: Any, user: User) -> Any:
        if self.exempt_roles.intersection(user.roles):
            return value
        return self.mask_fn(value, user)


# ---------------------------------------------------------------------------
# Helpers used by AccessControlManager
# ---------------------------------------------------------------------------

def filter_rows(
    policies: List[RLSPolicy],
    user: User,
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply RLS policies to a result set."""
    if not policies:
        return rows
    if "admin" in user.roles:
        return rows

    has_permissive = any(p.policy_type == "permissive" for p in policies)

    result: List[Dict[str, Any]] = []
    for row in rows:
        permissive_ok = False
        restrictive_block = False

        for pol in policies:
            if pol.policy_type == "permissive":
                if pol.evaluate(row, user):
                    permissive_ok = True
            else:
                if not pol.evaluate(row, user):
                    restrictive_block = True

        if has_permissive and not permissive_ok:
            continue
        if restrictive_block:
            continue
        result.append(row)

    return result


def apply_column_masks(
    masks: Dict[str, ColumnMask],
    user: User,
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Apply column masks to a result set."""
    if not masks:
        return rows
    if "admin" in user.roles:
        return rows

    masked: List[Dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        for col, mask in masks.items():
            if col in new_row:
                new_row[col] = mask.apply(new_row[col], user)
        masked.append(new_row)
    return masked
