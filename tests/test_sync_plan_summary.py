from redfetch.sync import build_plan_summary
from redfetch.sync_types import PlannedAction


def _action(
    target_key: str,
    resource_id: str,
    *,
    action: str,
    reason: str,
    title: str,
):
    return PlannedAction(
        target_key=target_key,
        resource_id=resource_id,
        parent_id=None,
        parent_target_key=None,
        root_resource_id=resource_id,
        target_kind="root",
        action=action,
        reason=reason,
        title=title,
        category_id=8,
        remote_version=1,
        artifact=None,
        resolved_path="C:/downloads",
        subfolder=None,
        flatten=False,
        protected_files=[],
        explicit_root=False,
    )


def test_build_plan_summary_groups_download_and_quiet_sections():
    plan = type(
        "_Plan",
        (),
        {
            "actions": {
                "/100/": _action("/100/", "100", action="download", reason="outdated", title="MQ2Shaman"),
                "/101/": _action("/101/", "101", action="block", reason="no_files", title="Maps Pack"),
                "/102/": _action("/102/", "102", action="block", reason="license_expired", title="Paid Plugin"),
            },
            "action_counts": lambda self: {"download": 1, "skip": 0, "block": 2, "untrack": 0},
        },
    )()

    summary = build_plan_summary(plan)

    assert summary.resources_in_scope == 3
    assert summary.resources_to_download == 1
    assert [section.label for section in summary.sections] == [
        "Resources to download",
        "Resources with no files",
        "Licenses expired",
    ]
    assert summary.sections[0].items[0].title == "MQ2Shaman"
    assert summary.sections[1].items[0].title == "Maps Pack"
    assert summary.sections[2].items[0].title == "Paid Plugin"
