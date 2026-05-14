from __future__ import annotations

from datetime import datetime, timezone

from proof_of_action.boundary import (
    OpenhumanView,
    PrivateDraft,
    PROJECTION_REGISTRY,
    PublicArtifactView,
    VapiView,
    _register_projection,
    projection_spec,
)


def test_public_views_are_registered():
    assert set(PROJECTION_REGISTRY) == {
        "OpenhumanView",
        "PublicArtifactView",
        "VapiView",
    }


def test_registered_fields_match_public_view_models():
    for view_type in (PublicArtifactView, OpenhumanView, VapiView):
        spec = projection_spec(view_type)

        assert spec.source_sensitivity == "private"
        assert spec.allowed_fields == frozenset(view_type.model_fields)


def test_projection_registry_records_target_planes_and_verifier_policies():
    assert projection_spec(PublicArtifactView).target_plane == "cited_artifact"
    assert projection_spec(PublicArtifactView).verifier_policy == "hash_refs_only"

    assert projection_spec(OpenhumanView).target_plane == "openhuman"
    assert projection_spec(OpenhumanView).verifier_policy == "hash_refs_only"

    assert projection_spec(VapiView).target_plane == "vapi_voice"
    assert projection_spec(VapiView).verifier_policy == "tts_safe_script"


def test_projection_registry_is_read_only_and_rejects_duplicates():
    spec = projection_spec(PublicArtifactView)

    try:
        PROJECTION_REGISTRY["Other"] = spec  # type: ignore[index]
        raise AssertionError("registry should be read-only")
    except TypeError:
        pass

    try:
        _register_projection(spec)
        raise AssertionError("duplicate registration should fail")
    except ValueError as exc:
        assert "duplicate projection registration" in str(exc)


def test_vapi_projection_normalizes_caller_supplied_topic_label():
    draft = PrivateDraft(
        action_id="act_001",
        thread_id="thread_001",
        body="Private draft about the Acme acquisition timing.",
        model="test",
        generated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )

    view = VapiView.project(draft, "Acme acquisition timing")

    assert view.topic_label == "a follow-up"
    assert "Acme acquisition" not in view.script
    assert "a follow-up" in view.script
