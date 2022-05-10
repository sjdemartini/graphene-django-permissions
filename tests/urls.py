from django.urls import path
from graphene_django.views import GraphQLView

from tests.schema import schema
from tests.schema_relay import schema as schema_relay

urlpatterns = [
    path("graphql/", GraphQLView.as_view(schema=schema)),
    path("graphql-relay/", GraphQLView.as_view(schema=schema_relay)),
]
