import graphene
import graphene_django_optimizer as gql_optimizer
from django.contrib.auth.models import User as UserModel
from graphene import Node, Schema
from graphene_django import DjangoConnectionField, DjangoObjectType
from graphql_relay import from_global_id

from tests import models


class ProjectNode(DjangoObjectType):
    class Meta:
        model = models.Project
        interfaces = (Node,)


class ExpenseNode(DjangoObjectType):
    class Meta:
        model = models.Expense
        interfaces = (Node,)


class UserNode(DjangoObjectType):
    class Meta:
        model = UserModel
        interfaces = (Node,)


class Query(graphene.ObjectType):
    project = Node.Field(ProjectNode)
    expense = Node.Field(ExpenseNode)
    user = Node.Field(UserNode)

    projects = DjangoConnectionField(ProjectNode)

    @staticmethod
    def resolve_projects(root, info):
        return gql_optimizer.query(
            models.Project.objects.all(),
            info,
        )


class ProjectUpdateInput(graphene.InputObjectType):
    name = graphene.String(required=True)


class ProjectUpdateMutation(graphene.Mutation):
    project = graphene.Field(
        ProjectNode,
        required=True,
        description="The updated Project",
    )

    class Arguments:
        id = graphene.ID(required=True)
        input = ProjectUpdateInput(required=True)

    @classmethod
    def mutate(cls, root, info, id: str, input: ProjectUpdateInput):
        _, project_id = from_global_id(id)
        project = models.Project.objects.get(id=project_id)
        project.name = input.name
        project.save()
        return cls(project=project)


class Mutation(graphene.ObjectType):
    project_update = ProjectUpdateMutation.Field()


schema = Schema(query=Query, mutation=Mutation)
