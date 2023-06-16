# graphene-django-permissions

[![pypi](https://img.shields.io/pypi/v/graphene-django-permissions.svg)](https://pypi.org/project/graphene-django-permissions/)
[![python](https://img.shields.io/pypi/pyversions/graphene-django-permissions.svg)](https://pypi.org/project/graphene-django-permissions/)
[![Build Status](https://github.com/sjdemartini/graphene-django-permissions/actions/workflows/dev.yml/badge.svg)](https://github.com/sjdemartini/graphene-django-permissions/actions/workflows/dev.yml)
[![codecov](https://codecov.io/gh/sjdemartini/graphene-django-permissions/branch/main/graphs/badge.svg)](https://codecov.io/github/sjdemartini/graphene-django-permissions)

A performant, holistic view-permissions layer for `graphene` / `graphene-django`, which augments the python GraphQL API using Django's built-in permissioning system, such that it only returns models that the user is authorized to see, regardless of how their query or mutation is formed.

## Installation

```shell
pip install graphene-django-permissions
```

## Usage

In your Django `settings.py` file, update your [Graphene configuration](https://docs.graphene-python.org/projects/django/en/latest/settings/) to include the authorization middleware:

```python
GRAPHENE = {
    "SCHEMA": "path.to.schema.schema",
    "MIDDLEWARE": (
        "graphene_django_permissions.middleware.GrapheneAuthorizationMiddleware",
    ),
}
```

And you're all set!

At this point, Graphene/GraphQL will only return model data that users are permitted to see, based on their Django model-level `view` permissions (like `polls.view_poll` for returning `Poll` model objects).

If a user (or a group the user is in) is granted the view permissions to a model (e.g. via `user.user_permissions.add()`, such that `user.has_perm("polls.view_poll")` returns `True`), Graphene will continue returning _all_ instances of that model in its query and mutation responses. If the user does _not_ have that view permission generally, the authorization middleware will check that the user has object-level permissions via `user.has_perm()`, and only return specific instances which the user is allowed to see.

See [here](https://docs.djangoproject.com/en/4.0/topics/auth/default/#default-permissions) for info on Django's default model permissions, and [here](https://docs.djangoproject.com/en/4.0/topics/auth/customizing/#handling-object-permissions) for info on object permissions. Typically the object-level authorization backend is implemented with an external library, like the popular [django-guardian](https://github.com/django-guardian/django-guardian) or [django-rules](https://github.com/dfunckt/django-rules) packages.

### Requirements

* `python` (3.7+)
* `graphene-django`  (see compatibility table below)
* Graphene `Schema`s must **not** use Relay / Nodes (until https://github.com/sjdemartini/graphene-django-permissions/issues/1 is resolved)

### Compatibility

| graphene-django-permissions | graphene-django |
| --- | --- |
| 1.0.0+ | v3.0.2+ |
| 0.1.0 | v2 |

## Motivation

The power of GraphQL is that the client can ask for exactly what data they need. But with that capability comes a risk: the backend needs to ensure that no matter what fields the client requests, the API only returns data they're authorized to see.

For example, suppose you have a Django models as follows:

```python
class Expense(models.Model):
    creator = models.ForeignKey(User, related_name="expenses")
    amount = models.IntegerField()
```

And a corresponding Graphene/GraphQL schema like:
```python
class Expense(DjangoObjectType):
    class Meta:
        model = models.Expense

class User(DjangoObjectType):
    class Meta:
        model = models.User

class Query(graphene.ObjectType):
    user = graphene.Field(User, id=graphene.ID())
    expenses = graphene.List(graphene.NonNull(Expense), required=True)
```

While we could update our `resolve_expenses` method so that we only allow users to load `expenses` in that query if they have permission, this would be an incomplete solution. A user could still form a separate query like `query { user(id:42) { id, expenses { ... } } }` to "indirectly" gain access to expenses via that alternative entry-point, where the `expenses` resolver would not come into play. These relationships will exist throughout a GQL application via numerous models and arbitrarily deep nesting, so trying to perform authorization with resolvers alone will undoubtedly spell trouble.

Instead, we'd like to restrict viewing models no matter what query pattern the client uses, which is what `graphene-django-permissions` allows. Whether you need model-level or object-level permissioning, you can be sure that the logic is applied everywhere you attempt to return Django models.

This was originally inspired by the popular JS library, [graphql-shield](https://github.com/maticzav/graphql-shield), which uses a middleware-based approach for GraphQL authorization.

### What is this not?

This library/middleware is **not** used for restricting access to route-level checks (i.e., individual queries or mutations). Instead, it is designed to ensure that no matter which query or mutation is used, the data returned to the user only includes models they're authorized to see.

To apply permissioning to a particular query or mutation (for instance, to only allow certain users to mutate some model), you can use standard Graphene/python logic, like:

```python
class UpdateUser(graphene.Mutation):
    class Arguments:
        user_id = graphene.Int()

    @classmethod
    def mutate(cls, root, info, user_id):
        if info.context.user.id != user_id:
            raise Exception("You do not have permission to perform this action")
        ...
```

or use an approach like decorators from [django-graphql-jwt](https://django-graphql-jwt.domake.io/decorators.html), or the mutation `permissions` field in [graphene-django-cud](https://graphene-django-cud.readthedocs.io/en/latest/guide/permissions.html). These options (and the above code example with custom logic) are all complementary to `graphene-django-permissions`, since even if you restrict access for a user to _perform_ a given query or mutation, you still want to be confident that you only return data to a user if they're authorized to see it (no matter which fields they request in their query/mutation).

### Complementary/recommended projects

- [graphene-django-optimizer](https://github.com/tfoxy/graphene-django-optimizer): Essential for performant Django model-based graphql.
- [graphene-django-cud](https://github.com/tOgg1/graphene-django-cud): Highly recommended for dramatically reducing boilerplate in defining create/update/delete mutations, including specifying permissions for accessing them.

### Alternatives

There are a few alternative ways one could apply authorization logic with Graphene, as alluded to above, though they have some shortcomings that tend to make a middleware-approach like `graphene-django-permissions` a better option.

#### Filtering at the `ObjectType` level

The official [graphene-django docs recommend](https://docs.graphene-python.org/projects/django/en/latest/authorization/#global-filtering) recommend adding logic like:

```python
class PostNode(DjangoObjectType):
    class Meta:
        model = Post

    @classmethod
    def get_queryset(cls, queryset, info):
        if info.context.user.is_anonymous:
            return queryset.filter(published=True)
        return queryset
```

While this functionally might accomplish what you need (granted, you have to take care to ensure `get_queryset` is respected in all of your access patterns), it ends up hurting SQL performance dramatically if you're relying on a tool like [graphene-django-optimizer](https://github.com/tfoxy/graphene-django-optimizer) (which you should!). This is because if the `Post` model ends up being queried via some nested pattern (e.g. you fetch a list of users, and the `Post`s of every user), the `queryset.filter()` call in the example above will end up causing an N+1 query pattern, since it will issue a new query per nested "posts" list.

`graphene-django-permissions` avoids this problem by filtering in-memory, after the SQL queries have been performed, so the query patterns are not directly affected by authorization logic. While it would be nice/preferable to more deeply integrate into the SQL query generation to avoid fetching the non-permitted data in the first place, along the lines of what's possible in SQLAlchemy (like with [sqlalchemy-oso](https://www.osohq.com/post/graphql-authorization-graphene-sqlalchemy-oso)), this is seemingly much trickier to do with Django and GQL in a consistent and performant way. (If you have any ideas on how to achieve something like this, please suggest it!)

#### Other libraries

There are a few other libraries ([graphene-permissions](https://github.com/redzej/graphene-permissions), [django-graphene-permissions](https://github.com/taoufik07/django-graphene-permissions), [graphene-field-permission](https://github.com/daveoconnor/graphene-field-permission)) that support authorization/permissions, but they seem to share similar limitations in that (1) they do not support object-level permissions in a reasonable/performant way (e.g. see [this issue](https://github.com/redzej/graphene-permissions/issues/10)), and (2) they require every model `ObjectType` to be updated individually to apply permissioning.
