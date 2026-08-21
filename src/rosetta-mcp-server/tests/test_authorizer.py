"""Unit tests for the Authorizer service."""

import pytest
from ragflow_sdk.modules.dataset import DataSet

from rosetta_mcp.clients.dataset import DatasetLookup
from rosetta_mcp.config import RosettaConfig
from rosetta_mcp.context import CallContext
from rosetta_mcp.services.authorizer import Authorizer


class _FakeTeamAPI:
    def __init__(
        self,
        teams=None,
        members_by_tenant=None,
        list_teams_error=None,
        list_member_errors=None,
    ):
        self.teams = teams or []
        self.members_by_tenant = members_by_tenant or {}
        self.list_teams_error = list_teams_error
        self.list_member_errors = list_member_errors or {}
        self.list_team_calls = 0
        self.list_member_calls = []

    def list_teams(self):
        self.list_team_calls += 1
        if self.list_teams_error is not None:
            raise self.list_teams_error
        return list(self.teams)

    def list_team_members(self, tenant_id: str):
        self.list_member_calls.append(tenant_id)
        if tenant_id in self.list_member_errors:
            raise self.list_member_errors[tenant_id]
        return list(self.members_by_tenant.get(tenant_id, []))


_MISSING = object()


class _Dataset:
    def __init__(self, dataset_id: str, name: str, tenant_id: object = _MISSING):
        self.id = dataset_id
        self.name = name
        if tenant_id is not _MISSING:
            self.tenant_id = tenant_id


class _FakeDatasetLookup:
    def __init__(self, datasets):
        self.datasets = {dataset.name: dataset for dataset in datasets}
        self.get_calls = []

    def get_dataset(self, name=None, dataset_id=None):
        self.get_calls.append((name, dataset_id))
        if name is not None:
            return self.datasets.get(name)
        if dataset_id is not None:
            return next(
                (dataset for dataset in self.datasets.values() if dataset.id == dataset_id),
                None,
            )
        return None


class _Rag:
    def __init__(self, datasets):
        self.datasets = datasets

    def list_datasets(self, **kwargs):
        return list(self.datasets)


class _BrokenDatasetLookup:
    def get_dataset(self, **kwargs):
        raise ConnectionError("dataset lookup failed")


def _make_config(read_policy: str = "all") -> RosettaConfig:
    return RosettaConfig(
        server_url="https://example.test",
        version="r2",
        api_key="test-key",
        posthog_api_key="",
        posthog_host="https://eu.i.posthog.com",
        debug=False,
        root_filter=[],
        transport="stdio",
        http_host="0.0.0.0",
        http_port=8000,
        redis_url=None,
        fernet_key=None,
        allowed_origins=[],
        oauth_authorization_endpoint="",
        oauth_token_endpoint="",
        oauth_introspection_endpoint="",
        oauth_client_id="",
        oauth_client_secret="",
        oauth_base_url="",
        oauth_callback_path="/auth/callback",
        oauth_valid_scopes="",
        oauth_extra_scopes="",
        oauth_revocation_endpoint="",
        oauth_jwt_signing_key=None,
        oauth_mode="oauth",
        oauth_oidc_config_url="",
        oauth_required_scopes=None,
        read_policy=read_policy,
        user_email="rosetta@example.com",
    )


def _make_team_authorizer(team_api, datasets=None) -> Authorizer:
    if datasets is None:
        datasets = [_Dataset("dataset-1", "project-myapp", "tenant-1")]
    return Authorizer(
        read_policy="team",
        config=_make_config(),
        team_api=team_api,
        dataset_lookup=_FakeDatasetLookup(datasets),
    )


class TestAiaDatasets:
    """aia-* datasets: always readable."""

    @pytest.mark.parametrize("policy", ["all", "team", "none"])
    def test_aia_read_always_allowed(self, policy):
        auth = Authorizer(read_policy=policy, config=_make_config())
        assert auth.can_read("aia-r1", "user@example.com") is True

    def test_aia_r2(self):
        auth = Authorizer(read_policy="none", config=_make_config())
        assert auth.can_read("aia-r2", "user@example.com") is True


class TestProjectDatasetsAllPolicy:
    """project-* with policy=all."""

    def test_read_all(self):
        auth = Authorizer(read_policy="all", config=_make_config())
        assert auth.can_read("project-myapp", "anyone@example.com") is True


class TestProjectDatasetsNonePolicy:
    """project-* with policy=none."""

    def test_read_none(self):
        auth = Authorizer(read_policy="none", config=_make_config())
        assert auth.can_read("project-myapp", "user@example.com") is False


class TestProjectDatasetsTeamPolicy:
    """project-* with policy=team."""

    def test_missing_dataset_lookup_denies_without_team_api_call(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={"tenant-1": [{"email": "member@example.com"}]},
        )
        auth = Authorizer(read_policy="team", config=_make_config(), team_api=team_api)

        assert auth.can_read("project-myapp", "member@example.com") is False
        assert team_api.list_team_calls == 0

    def test_team_policy_denies_member_of_another_owner_team(self):
        team_api = _FakeTeamAPI(
            teams=[
                {"tenant_id": "tenant-a", "role": "owner"},
                {"tenant_id": "tenant-b", "role": "owner"},
            ],
            members_by_tenant={
                "tenant-a": [{"email": "member-a@example.com", "role": "normal"}],
                "tenant-b": [{"email": "member-b@example.com", "role": "normal"}],
            },
        )
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=team_api,
            dataset_lookup=_FakeDatasetLookup(
                [
                    _Dataset("dataset-a", "project-a", "tenant-a"),
                    _Dataset("dataset-b", "project-b", "tenant-b"),
                ]
            ),
        )

        assert auth.can_read("project-b", "member-a@example.com") is False
        assert team_api.list_member_calls == ["tenant-b"]

    def test_read_team_member(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={
                "tenant-1": [
                    {"email": "member@example.com", "role": "normal"},
                ]
            },
        )
        auth = _make_team_authorizer(team_api)
        assert auth.can_read("project-myapp", "member@example.com") is True

    def test_read_team_member_uses_sdk_dataset_tenant_id(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={"tenant-1": [{"email": "member@example.com"}]},
        )
        dataset = DataSet(
            _Rag([]),
            {
                "id": "dataset-1",
                "name": "project-myapp",
                "tenant_id": "tenant-1",
            },
        )
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=team_api,
            dataset_lookup=_FakeDatasetLookup([dataset]),
        )

        assert auth.can_read("project-myapp", "member@example.com") is True
        assert team_api.list_member_calls == ["tenant-1"]

    def test_read_team_pending_invite_is_authorized(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={
                "tenant-1": [
                    {"email": "invitee@example.com", "role": "invite"},
                ]
            },
        )
        auth = _make_team_authorizer(team_api)
        assert auth.can_read("project-myapp", "invitee@example.com") is True

    def test_team_policy_denies_non_member(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={"tenant-1": [{"email": "other@example.com", "role": "normal"}]},
        )
        auth = _make_team_authorizer(team_api)
        assert auth.can_read("project-myapp", "missing@example.com") is False

    def test_team_policy_propagates_api_errors(self):
        auth = _make_team_authorizer(
            _FakeTeamAPI(list_teams_error=RuntimeError("tenant lookup failed"))
        )
        with pytest.raises(RuntimeError, match="tenant lookup failed"):
            auth.can_read("project-myapp", "member@example.com")

    def test_member_of_multiple_teams_is_allowed_only_via_dataset_owner(self):
        team_api = _FakeTeamAPI(
            teams=[
                {"tenant_id": "tenant-a", "role": "owner"},
                {"tenant_id": "tenant-b", "role": "owner"},
            ],
            members_by_tenant={
                "tenant-a": [{"email": "shared@example.com"}],
                "tenant-b": [{"email": "shared@example.com"}],
            },
        )
        auth = _make_team_authorizer(
            team_api,
            datasets=[_Dataset("dataset-b", "project-myapp", "tenant-b")],
        )

        assert auth.can_read("project-myapp", "shared@example.com") is True
        assert team_api.list_member_calls == ["tenant-b"]

    @pytest.mark.parametrize("tenant_id", [None, "", "   ", 42])
    def test_missing_or_malformed_dataset_tenant_denies(self, tenant_id):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={"tenant-1": [{"email": "member@example.com"}]},
        )
        auth = _make_team_authorizer(
            team_api,
            datasets=[_Dataset("dataset-1", "project-myapp", tenant_id)],
        )

        assert auth.can_read("project-myapp", "member@example.com") is False
        assert team_api.list_team_calls == 0
        assert team_api.list_member_calls == []

    def test_dataset_without_tenant_attribute_denies(self):
        team_api = _FakeTeamAPI()
        auth = _make_team_authorizer(
            team_api,
            datasets=[_Dataset("dataset-1", "project-myapp")],
        )

        assert auth.can_read("project-myapp", "member@example.com") is False
        assert team_api.list_team_calls == 0

    def test_unknown_dataset_denies_without_team_api_call(self):
        team_api = _FakeTeamAPI()
        auth = _make_team_authorizer(team_api, datasets=[])

        assert auth.can_read("project-missing", "member@example.com") is False
        assert team_api.list_team_calls == 0

    def test_dataset_name_mismatch_denies(self):
        team_api = _FakeTeamAPI()
        lookup = _FakeDatasetLookup([])
        lookup.datasets["project-requested"] = _Dataset(
            "dataset-other", "project-other", "tenant-1"
        )
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=team_api,
            dataset_lookup=lookup,
        )

        assert auth.can_read("project-requested", "member@example.com") is False
        assert team_api.list_team_calls == 0

    def test_ambiguous_dataset_name_denies(self):
        team_api = _FakeTeamAPI(
            teams=[
                {"tenant_id": "tenant-a", "role": "owner"},
                {"tenant_id": "tenant-b", "role": "owner"},
            ],
            members_by_tenant={"tenant-a": [{"email": "member@example.com"}]},
        )
        lookup = DatasetLookup(
            ragflow=_Rag(
                [
                    _Dataset("dataset-a", "project-shared", "tenant-a"),
                    _Dataset("dataset-b", "project-shared", "tenant-b"),
                ]
            )
        )
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=team_api,
            dataset_lookup=lookup,
        )

        assert auth.can_read("project-shared", "member@example.com") is False
        assert team_api.list_team_calls == 0

    @pytest.mark.parametrize(
        "teams",
        [
            [],
            [None, {}, {"tenant_id": 42, "role": "owner"}],
            [{"tenant_id": "tenant-1", "role": "normal"}],
            [{"tenant_id": "another-tenant", "role": "owner"}],
        ],
    )
    def test_missing_or_malformed_owner_team_denies(self, teams):
        team_api = _FakeTeamAPI(teams=teams)
        auth = _make_team_authorizer(team_api)

        assert auth.can_read("project-myapp", "member@example.com") is False
        assert team_api.list_member_calls == []

    def test_malformed_member_entries_deny(self):
        team_api = _FakeTeamAPI(
            teams=[{"tenant_id": "tenant-1", "role": "owner"}],
            members_by_tenant={"tenant-1": [None, {}, {"email": None}]},
        )
        auth = _make_team_authorizer(team_api)

        assert auth.can_read("project-myapp", "member@example.com") is False

    @pytest.mark.parametrize(
        "error",
        [RuntimeError("member lookup failed"), TimeoutError("member lookup timed out")],
    )
    def test_team_policy_propagates_member_api_errors(self, error):
        auth = _make_team_authorizer(
            _FakeTeamAPI(
                teams=[{"tenant_id": "tenant-1", "role": "owner"}],
                list_member_errors={"tenant-1": error},
            )
        )

        with pytest.raises(type(error), match=str(error)):
            auth.can_read("project-myapp", "member@example.com")

    def test_team_policy_propagates_dataset_lookup_errors(self):
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=_FakeTeamAPI(),
            dataset_lookup=_BrokenDatasetLookup(),
        )

        with pytest.raises(ConnectionError, match="dataset lookup failed"):
            auth.can_read("project-myapp", "member@example.com")

    def test_empty_user_email_denies_without_external_calls(self):
        team_api = _FakeTeamAPI()
        lookup = _FakeDatasetLookup(
            [_Dataset("dataset-1", "project-myapp", "tenant-1")]
        )
        auth = Authorizer(
            read_policy="team",
            config=_make_config(),
            team_api=team_api,
            dataset_lookup=lookup,
        )

        assert auth.can_read("project-myapp", "  ") is False
        assert lookup.get_calls == []
        assert team_api.list_team_calls == 0


def test_call_context_default_authorizer_uses_context_dataset_lookup(monkeypatch):
    team_api = _FakeTeamAPI(
        teams=[{"tenant_id": "tenant-1", "role": "owner"}],
        members_by_tenant={"tenant-1": [{"email": "member@example.com"}]},
    )
    monkeypatch.setattr(
        "rosetta_mcp.services.authorizer.RAGFlowTeamAPI.from_config",
        lambda config: team_api,
    )
    lookup = _FakeDatasetLookup(
        [_Dataset("dataset-1", "project-myapp", "tenant-1")]
    )
    call_context = CallContext(
        config=_make_config(read_policy="team"),
        ragflow=_Rag([]),
        dataset_lookup=lookup,
        ctx=None,
        username="tester",
        repository="example/repo",
        tool_name="query_instructions",
        params={},
        user_email="member@example.com",
    )

    assert call_context.authorizer.can_read("project-myapp", "member@example.com") is True
    assert team_api.list_member_calls == ["tenant-1"]
