"""Policy-based authorization for dataset access."""

from __future__ import annotations

from rosetta_mcp.clients.dataset import DatasetLookup
from rosetta_mcp.config import RosettaConfig
from rosetta_mcp.constants import POLICY_ALL, POLICY_NONE, POLICY_TEAM
from rosetta_mcp.services._ragflow_team_api import RAGFlowTeamAPI


def _normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


class Authorizer:
    """Enforces read policies on datasets.

    Rules:
        - ``aia-*`` datasets: read always allowed.
        - ``project-*`` datasets: governed by *read_policy*.
        - Policy ``all``  → everybody.
        - Policy ``team`` → members or pending invites in the dataset owner's team.
        - Policy ``none`` → nobody.
    """

    def __init__(
        self,
        read_policy: str,
        *,
        config: RosettaConfig,
        team_api: RAGFlowTeamAPI | None = None,
        dataset_lookup: DatasetLookup | None = None,
    ) -> None:
        self._read_policy = read_policy
        self._config = config
        self._team_api = team_api
        self._dataset_lookup = dataset_lookup

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def can_read(self, dataset_name: str, user_email: str) -> bool:
        if _is_aia(dataset_name):
            return True
        return self._evaluate(self._read_policy, dataset_name, user_email)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evaluate(self, policy: str, dataset_name: str, user_email: str) -> bool:
        if policy == POLICY_ALL:
            return True
        if policy == POLICY_NONE:
            return False
        if policy == POLICY_TEAM:
            normalized_email = _normalize_email(user_email)
            if not normalized_email or self._dataset_lookup is None:
                return False
            tenant_id = _resolve_dataset_tenant(dataset_name, self._dataset_lookup)
            if tenant_id is None:
                return False
            return _check_team_membership(
                tenant_id,
                normalized_email,
                team_api=self._get_team_api(),
            )
        return False

    def _get_team_api(self) -> RAGFlowTeamAPI:
        if self._team_api is None:
            self._team_api = RAGFlowTeamAPI.from_config(self._config)
        return self._team_api


def _is_aia(dataset_name: str) -> bool:
    return dataset_name.startswith("aia-")


def _resolve_dataset_tenant(
    dataset_name: str,
    dataset_lookup: DatasetLookup,
) -> str | None:
    """Resolve the requested dataset's authoritative owning tenant."""
    dataset = dataset_lookup.get_dataset(name=dataset_name)
    if dataset is None or getattr(dataset, "name", None) != dataset_name:
        return None

    tenant_id = getattr(dataset, "tenant_id", None)
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        return None
    return tenant_id.strip()


def _check_team_membership(
    tenant_id: str,
    normalized_email: str,
    *,
    team_api: RAGFlowTeamAPI,
) -> bool:
    """Check whether an email belongs to the exact owning tenant."""

    teams = team_api.list_teams()
    owner_team = next(
        (
            team
            for team in teams
            if isinstance(team, dict)
            and isinstance(team.get("tenant_id"), str)
            and team["tenant_id"].strip() == tenant_id
            and str(team.get("role", "")).strip().lower() == "owner"
        ),
        None,
    )
    if owner_team is None:
        return False

    members = team_api.list_team_members(tenant_id)
    for member in members:
        if isinstance(member, dict) and _normalize_email(member.get("email")) == normalized_email:
            return True

    return False
