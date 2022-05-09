from django.urls import path
from graphene_django.views import GraphQLView

from tests.schema import schema

urlpatterns = [
    path("graphql/", GraphQLView.as_view(schema=schema)),
]
