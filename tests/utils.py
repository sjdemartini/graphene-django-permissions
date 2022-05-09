import json
from typing import Iterable

from django.contrib.auth.models import Permission, User
from django.http import HttpResponse


def assert_graphql_response_has_no_errors(response: HttpResponse):
    assert (
        response.status_code == 200
    ), f"Response status unexpectedly {response.status_code}: {repr(response.content)}"

    content = json.loads(response.content)
    assert "errors" not in list(
        content.keys()
    ), f"Response unexpectedly contains errors: {content.get('errors')}"


def assert_graphql_response_has_errors(response: HttpResponse):
    content = json.loads(response.content)
    assert "errors" in list(
        content.keys()
    ), f"Response unexpectedly does NOT contain errors: {content}"


def _get_permission_from_string(perm: str) -> Permission:
    if "." not in perm:
        raise ValueError(
            f'Invalid permission "{perm}". Must be of the form'
            ' <app_label.permission_codename>, like "polls.view_poll".'
        )

    app_label, codename = perm.split(".")

    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def add_permissions_for_user(user: User, permissions: Iterable[str]) -> None:
    """
    Grant the user the given permissions.

    Parameters
    ----------
    user : User
        The user for whom we're adding permissions to.
    permissions : Iterable[str]
        A list of permissions the user should have, each a string of the form:
        <app_label.permission_codename>, like "polls.view_poll".
    """
    permission_objects = [
        _get_permission_from_string(permission_str) for permission_str in permissions
    ]
    user.user_permissions.add(*permission_objects)
