# graphene-django-permissions

[![pypi](https://img.shields.io/pypi/v/graphene-django-permissions.svg)](https://pypi.org/project/graphene-django-permissions/)
[![python](https://img.shields.io/pypi/pyversions/graphene-django-permissions.svg)](https://pypi.org/project/graphene-django-permissions/)
[![Build Status](https://github.com/sjdemartini/graphene-django-permissions/actions/workflows/dev.yml/badge.svg)](https://github.com/sjdemartini/graphene-django-permissions/actions/workflows/dev.yml)
[![codecov](https://codecov.io/gh/sjdemartini/graphene-django-permissions/branch/main/graphs/badge.svg)](https://codecov.io/github/sjdemartini/graphene-django-permissions)

A performant, holistic permissions layer for `graphene` / `graphene-django`, which prevents the GraphQL API from returning any models that the user is not authorized to view, regardless of how the query or mutation is formed.

## Usage

```shell
pip install graphene-django-permissions
```

Then in your Django `settings.py` file, update your [Graphene configuration](https://docs.graphene-python.org/projects/django/en/latest/settings/) to include the authorization middleware:

```python
GRAPHENE = {
    "SCHEMA": "path.to.schema.schema",
    # https://docs.graphene-python.org/projects/django/en/latest/settings/#middleware
    "MIDDLEWARE": (
        "graphene_django_permissions.middleware.GrapheneAuthorizationMiddleware",
    ),
}
```

And you're all set!

At this point, Graphene/GraphQL will only return model data that users are permitted to see, based on their Django model-level `view` permissions (like `polls.view_poll`).

If a user (or a group the user is in) is granted the view permissions to a model directly (e.g. via `user.user_permissions.add()`, such that `user.has_perm("polls_view_poll")` returns `True`), Graphene will continue returning _all_ instances of that model in its query and mutation responses. If the user does _not_ have that view permission generally, the authorization middleware will check that the user has object-level permissions via `user.has_perm()`, and only return specific instances which the user is allowed to see.

See [here](https://docs.djangoproject.com/en/4.0/topics/auth/default/#default-permissions) for info on Django's default model permissions, and [here](https://docs.djangoproject.com/en/4.0/topics/auth/customizing/#handling-object-permissions) for info on object permissions. Typically the object-level authorization backend is implemented with an external library, like the popular [django-guardian](https://github.com/django-guardian/django-guardian) or [django-rules](https://github.com/dfunckt/django-rules).

### Requirements

* `graphene-django` version 2 (until https://github.com/sjdemartini/graphene-django-permissions/issues/2 is resolved)
* Graphene `Schema`s must **not** use Relay / Nodes (until https://github.com/sjdemartini/graphene-django-permissions/issues/1 is resolved)
