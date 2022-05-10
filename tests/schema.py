import graphene
import graphene_django_optimizer as gql_optimizer
from django.contrib.auth.models import User as UserModel
from graphene import Schema
from graphene_django import DjangoObjectType

from tests import models

# Types


class Project(DjangoObjectType):
    class Meta:
        model = models.Project


class Expense(DjangoObjectType):
    class Meta:
        model = models.Expense


class User(DjangoObjectType):
    class Meta:
        model = UserModel


# Queries


class Query(graphene.ObjectType):
    project = graphene.Field(Project, id=graphene.ID())
    expense = graphene.Field(Expense, id=graphene.ID())

    projects = graphene.List(graphene.NonNull(Project), required=True)
    projects_list = graphene.List(graphene.NonNull(Project), required=True)
    expenses = graphene.List(graphene.NonNull(Expense), required=True)
    users = graphene.List(graphene.NonNull(User), required=True)

    @staticmethod
    def resolve_project(root, info, id: str):
        try:
            return gql_optimizer.query(
                models.Project.objects.all().filter(id=id),
                info,
            ).get()
        except models.Project.DoesNotExist:
            return None

    @staticmethod
    def resolve_expense(root, info, id: str):
        try:
            return gql_optimizer.query(
                models.Expense.objects.all().filter(id=id),
                info,
            ).get()
        except models.Expense.DoesNotExist:
            return None

    @staticmethod
    def resolve_projects(root, info):
        return gql_optimizer.query(
            models.Project.objects.all(),
            info,
        )

    @staticmethod
    def resolve_projects_list(root, info):
        # This query returns project objects as a list rather than a queryset, useful
        # for ensuring our authorization middleware performs proper permissioning even
        # in this scenario
        return list(
            gql_optimizer.query(
                models.Project.objects.all(),
                info,
            )
        )

    @staticmethod
    def resolve_expenses(root, info):
        return gql_optimizer.query(
            models.Expense.objects.all(),
            info,
        )

    @staticmethod
    def resolve_users(root, info):
        return gql_optimizer.query(
            models.User.objects.all(),
            info,
        )


# Mutations


class ProjectUpdateInput(graphene.InputObjectType):
    name = graphene.String(required=True)


class ProjectUpdateMutation(graphene.Mutation):
    project = graphene.Field(
        Project,
        required=True,
        description="The updated Project",
    )

    class Arguments:
        id = graphene.ID(required=True)
        input = ProjectUpdateInput(required=True)

    @classmethod
    def mutate(cls, root, info, id: str, input: ProjectUpdateInput):
        project = models.Project.objects.get(id=id)
        project.name = input.name
        project.save()
        return cls(project=project)


class Mutation(graphene.ObjectType):
    project_update = ProjectUpdateMutation.Field()


schema = Schema(query=Query, mutation=Mutation)
