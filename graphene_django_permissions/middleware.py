from typing import Type

import graphql
from django.db import models


class PermissionDenied(graphql.GraphQLError):
    pass


def get_permission_for_model(model: Type[models.Model], action: str) -> str:
    app_label = model._meta.app_label
    model_name = model._meta.model_name
    return f"{app_label}.{action}_{model_name}"


def get_view_permission_for_model(model: Type[models.Model]) -> str:
    return get_permission_for_model(model, "view")


def has_permission_to_view_model_object(user, object: models.Model) -> bool:
    model = object._meta.model
    # Check if the user has access to all objects for this model, or this specific
    # object.
    permission = get_view_permission_for_model(model)
    return user.has_perm(permission) or user.has_perm(permission, obj=object)


class GrapheneAuthorizationMiddleware:
    """
    This adds model-level view-authorization logic to Graphene, where for each model in
    the response, it requires the user to have the default view permission for that
    model.
    """

    def resolve(self, next, root, info, **args):
        # First, get the result for this node in the response
        result = next(root, info, **args)

        # Given the resulting value, check whether the current user has view access
        if isinstance(result.value, models.Model):
            if not has_permission_to_view_model_object(info.context.user, result.value):
                # The user does not have access to all objects for this model, nor this
                # specific object. As such, return null for this field.

                if isinstance(info.return_type, graphql.GraphQLNonNull):
                    # If this field the client requested (but doesn't have access to) is
                    # non-nullable in the GraphQL schema, then we're forced to raise an
                    # error, since we can't circumvent the schema at the authorization
                    # layer. The rest of the separate authorized data that satisfies the
                    # GQL schema will still be returned and appear as normal.
                    raise PermissionDenied(
                        "You do not have permission to access this field"
                    )

                return None

        elif isinstance(result.value, models.QuerySet):
            model = result.value.model
            permission = get_view_permission_for_model(model)
            if not info.context.user.has_perm(permission):
                # The user does not have access to all objects for this model, so we'll
                # filter to only the specific objects the user can access. Note that we
                # are implicitly converting the queryset to a list by doing so. This is
                # intentional, since the query will already have been evaluated and
                # optimized from the top-level (if graphene_django_optimizer is used),
                # so we effectively pay no SQL cost by iterating through the results
                # here, unlike if we were to use a `filter` on the queryset or similar.
                return [
                    obj
                    for obj in result.value
                    if info.context.user.has_perm(permission, obj=obj)
                ]

        elif isinstance(result.value, (list, tuple, set)):
            # Sometimes queries may return a list or other iterable of models, rather
            # than a QuerySet of models (e.g., if they performed some in-memory
            # filtering on a queryset and implicitly converted to a list themselves). In
            # this case, we should still attempt to check permissions on the individual
            # objects. We'll allow (1) any object that isn't a model object or (2) any
            # model object that the user has permission to view.
            return [
                obj
                for obj in result.value
                if not isinstance(obj, models.Model)
                or has_permission_to_view_model_object(info.context.user, obj)
            ]

        return result
