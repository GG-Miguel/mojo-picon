import pytest

from mojo_picon.auth import FirebaseTokenVerifier, InvalidTokenError, UserContext, bearer_token


@pytest.mark.parametrize(
    ("header", "token"), [("Bearer abc.def.ghi", "abc.def.ghi"), ("bearer  abc ", "abc"), ("BEARER x", "x")]
)
def test_bearer_token(header, token):
    assert bearer_token(header) == token


@pytest.mark.parametrize("header", [None, "", "Basic abc", "Bearer", "Bearer   ", "abc"])
def test_bearer_token_rejects_other_headers(header):
    with pytest.raises(InvalidTokenError):
        bearer_token(header)


def test_user_context_defaults():
    ctx = UserContext(uid="ana")
    assert ctx.roles == frozenset({"user"})
    assert ctx.timezone == "Atlantic/Canary"


@pytest.fixture
def verifier(monkeypatch):
    import firebase_admin
    from firebase_admin import auth

    calls = {}

    def fake_verify(token, app=None, check_revoked=False):
        calls["check_revoked"] = check_revoked
        if token == "good":
            return {"uid": "ana"}
        if token == "admin":
            return {"uid": "boss", "admin": True}
        raise auth.InvalidIdTokenError("bad token", cause=None)

    monkeypatch.setattr(auth, "verify_id_token", fake_verify)
    monkeypatch.setattr(firebase_admin, "get_app", lambda: object())
    v = FirebaseTokenVerifier(project_id="test-project")
    v.calls = calls
    return v


async def test_firebase_verifier_returns_the_uid_from_the_token(verifier):
    ctx = await verifier.verify("good")
    assert ctx == UserContext(uid="ana")
    assert verifier.calls["check_revoked"] is True


async def test_firebase_verifier_maps_the_admin_claim_to_a_role(verifier):
    assert "admin" in (await verifier.verify("admin")).roles


@pytest.mark.parametrize("token", ["", "forged"])
async def test_firebase_verifier_rejects_invalid_tokens(verifier, token):
    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_disabled_accounts_get_401_not_500(monkeypatch):
    import firebase_admin
    from firebase_admin import auth

    def disabled(token, app=None, check_revoked=False):
        raise auth.UserDisabledError("disabled")

    monkeypatch.setattr(auth, "verify_id_token", disabled)
    monkeypatch.setattr(firebase_admin, "get_app", lambda: object())
    with pytest.raises(InvalidTokenError):
        await FirebaseTokenVerifier(project_id="p").verify("token")
