import json
import re

import pytest
from django.contrib.auth.backends import BaseBackend
from django.test.client import Client
from graphene_django.utils.testing import graphql_query

from tests.factories import ExpenseFactory, ProjectFactory, UserFactory
from tests.utils import (
    assert_graphql_response_has_errors,
    assert_graphql_response_has_no_errors,
)

pytestmark = pytest.mark.django_db


# For testing object-level permissions, we'll implement our own authorization backend
# that allows an object's "owner" to view it, even if they do not have sweeping
# model-level view permissions. (See note here
# https://docs.djangoproject.com/en/4.0/topics/auth/customizing/#handling-object-permissions
# about handling object permissions in Django. Typically the authorization backend would
# be implemented with a library like https://github.com/django-guardian/django-guardian
# or https://github.com/dfunckt/django-rules.)
class OwnerPermittedAuthBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if not obj:
            return super().has_perm(user_obj, perm, obj)

        if perm == "tests.view_project" or perm == "tests.view_expense":
            # Allow a user access to view the specific object if they're the owner of
            # that object
            return obj.owner_id == user_obj.id

        return super().has_perm(user_obj, perm, obj)


@pytest.fixture
def use_owner_permitted_auth_backend(settings):
    """
    Add the object-level permissioning authorization backend to the configured backends
    in Django.
    """
    settings.AUTHENTICATION_BACKENDS = [
        *settings.AUTHENTICATION_BACKENDS,
        "test_middleware.OwnerPermittedAuthBackend",
    ]


class TestGrapheneAuthorizationMiddleware:
    """
    Test that the Graphene authorization middleware properly restricts read access
    depending on user permissions.
    """

    def _project_query(self):
        return """
            query ($id: ID!) {
                project(id: $id) {
                    id
                    name

                    owner {
                        id
                        username
                    }

                    expenses {
                        amount
                        id

                        owner {
                            id
                            username
                        }
                    }
                }
            }
        """

    def _projects_with_expenses_query(self):
        return """
            query ProjectsQuery {
                projects {
                    id
                    name

                    owner {
                        id
                        username
                    }

                    expenses {
                        amount
                        id

                        owner {
                            id
                            username
                        }
                    }
                }
            }
        """

    def _project_with_owner_expenses_query(self):
        # Include nested list of expenses for each project's owner
        return """
            query ($id: ID!) {
                project(id: $id) {
                    id
                    name

                    owner {
                        id
                        username

                        expenses {
                            amount
                            id

                            owner {
                                id
                                username
                            }
                        }
                    }
                }
            }
        """

    def _projects_returning_list_query(self):
        # This query is useful to test a response resolver that returns a list rather
        # than a QuerySet
        return """
            query {
                projectsList {
                    id
                    name

                    owner {
                        id
                        username
                    }

                    expenses {
                        amount
                        id
                    }
                }
            }
        """

    def _expense_query(self):
        return """
            query ($id: ID!) {
                expense(id: $id) {
                    amount
                    id

                    project {
                        id
                        name

                        owner {
                            id
                            username
                        }
                    }
                }
            }
        """

    def _project_mutation(self):
        # This mutation is useful to let us verify that we enforce authorization even
        # for responses from mutations
        return """
            mutation (
                $id: ID!,
                $input: ProjectUpdateInput!
            ) {
                projectUpdate(id: $id, input: $input) {
                    project {
                        id
                        name

                        owner {
                            id
                            username
                        }

                        expenses {
                            amount
                            id

                            owner {
                                id
                                username
                            }
                        }
                    }
                }
            }
        """

    def test_top_level_list_and_its_children_are_non_empty_when_have_all_permissions(
        self, client: Client
    ):
        """
        When querying for a list of objects, the list should be non-empty if the user
        has permission, and its various children should be included with permission to
        those.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(5, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)

        response = graphql_query(
            query=self._projects_with_expenses_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]

        # All of the projects and expenses should be visible, with their associated user
        # data
        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        project1_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project1.id)
        )
        assert project1_in_response["owner"] is not None
        assert len(project1_in_response["expenses"]) == 5
        assert project1_in_response["expenses"][0]["owner"] is not None

        project2_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project2.id)
        )
        assert project2_in_response["owner"] is not None
        assert len(project2_in_response["expenses"]) == 2

    def test_top_level_list_and_its_children_are_non_empty_when_user_is_superuser(
        self, client: Client
    ):
        # Don't assign any specific permissions to a user, just mark them as a superuser
        user = UserFactory(is_superuser=True)
        client.force_login(user)

        project1 = ProjectFactory()
        ExpenseFactory.create_batch(5, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)

        response = graphql_query(
            query=self._projects_with_expenses_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]

        # All of the projects and expenses should be visible
        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        project1_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project1.id)
        )
        assert project1_in_response["owner"] is not None
        assert len(project1_in_response["expenses"]) == 5
        assert project1_in_response["expenses"][0]["owner"] is not None

        project2_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project2.id)
        )
        assert len(project2_in_response["expenses"]) == 2

    def test_top_level_list_field_is_empty_without_permission(self, client: Client):
        """
        When querying for a top-level List field, the list should be empty if the user
        does not have permission to that model.
        """
        # Exclude permissions to view projects, the top-level model
        user = UserFactory(
            permissions=[
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        response = graphql_query(
            self._projects_with_expenses_query(),
            client=client,
        )

        # There should be no errors, but the top-level list should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        assert len(content["data"]["projects"]) == 0

    @pytest.mark.usefixtures("use_owner_permitted_auth_backend")
    def test_top_level_list_field_contains_owned_objects_with_object_level_permissions(
        self, client: Client
    ):
        """
        When querying for a top-level List field, the list should contain objects that
        are owned by the current user, respecting the custom object-permission
        authorization backend when it's in place.
        """
        # Exclude permissions to view projects, the top-level model
        user = UserFactory(
            permissions=[
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Mark the requesting user as the owner of one project, and only that one should
        # be returned
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)
        project3 = ProjectFactory(owner=user)  # Owned by the requesting user
        ExpenseFactory.create_batch(2, project=project3)

        response = graphql_query(
            self._projects_with_expenses_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        assert len(content["data"]["projects"]) == 1
        assert content["data"]["projects"][0]["id"] == str(project3.id)
        assert len(content["data"]["projects"][0]["expenses"]) == 2

    def test_top_level_list_field_is_empty_for_anonymous_user_without_permission(
        self, client: Client
    ):
        """
        When querying for a top-level List field, the list should be empty if there
        isn't a user logged in (an AnonymousUser), who does not have permission to that
        model.
        """
        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        # Don't log in any user to the client. The "AnonymousUser" should not have
        # permission to view any projects
        response = graphql_query(
            self._projects_with_expenses_query(),
            client=client,
        )

        # There should be no errors, but the top-level list should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        assert len(content["data"]["projects"]) == 0

    def test_top_level_object_field_is_non_empty_with_permission(self, client: Client):
        """
        When querying for a single object field, it should be returned if the user has
        permission to that model.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        response = graphql_query(
            self._project_query(),
            variables={
                "id": project.id,
            },
            client=client,
        )

        # There should be no errors, but the top-level object should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        project_in_response = content["data"]["project"]
        assert project_in_response is not None
        assert project_in_response["id"] == str(project.id)
        assert project_in_response["owner"] is not None
        assert len(project_in_response["expenses"]) == 2
        assert project_in_response["expenses"][0]["owner"] is not None

    def test_top_level_object_field_is_null_without_permission(self, client: Client):
        """
        When querying for a top-level object field, it should be returned as null if the
        user does not have permission to that model.
        """
        # Exclude permissions to view projects, the top-level model
        user = UserFactory(
            permissions=[
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        response = graphql_query(
            self._project_query(),
            variables={
                "id": project.id,
            },
            client=client,
        )

        # There should be no errors, but the top-level object should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        assert content["data"]["project"] is None

    def test_nested_related_model_list_is_empty_when_missing_permissions(
        self, client: Client
    ):
        """
        When a user doesn't have permission for a nested model that's returned as a
        list, the list should be empty.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(5, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)

        response = graphql_query(
            query=self._projects_with_expenses_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]

        # The projects should show up, but expenses should be empty
        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        assert len(projects_in_response[0]["expenses"]) == 0
        assert len(projects_in_response[1]["expenses"]) == 0

    @pytest.mark.usefixtures("use_owner_permitted_auth_backend")
    def test_nested_related_model_list_includes_owned_objects_with_object_level_permission(
        self, client: Client
    ):
        """
        Verify that for queried nested/related lists, we return objects that are owned
        by the current user, respecting the custom object-permission authorization
        backend when it's in place.
        """
        # Omit the model-level expenses view-permission
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them, including some owned by the
        # requesting user
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project1_user_owned_expenses = ExpenseFactory.create_batch(
            2, project=project1, owner=user
        )
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)
        project2_user_owned_expenses = ExpenseFactory.create_batch(
            1, project=project2, owner=user
        )

        response = graphql_query(
            query=self._projects_with_expenses_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]

        # The projects should show up, and the list of expenses should match the ones
        # owned by the user
        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        project1_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project1.id)
        )
        assert project1_in_response["owner"] is not None
        assert len(project1_in_response["expenses"]) == 2
        assert {expense["id"] for expense in project1_in_response["expenses"]} == {
            str(expense.id) for expense in project1_user_owned_expenses
        }

        project2_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project2.id)
        )
        assert project2_in_response["owner"] is not None
        assert len(project2_in_response["expenses"]) == 1
        assert {expense["id"] for expense in project2_in_response["expenses"]} == {
            str(expense.id) for expense in project2_user_owned_expenses
        }

    def test_nested_related_model_list_within_child_is_non_empty_with_permission_to_model(
        self, client: Client
    ):
        """
        Verify that we return a list as non-empty if the user has access to that model,
        even if that list is within a child's relations (nested deeper).
        """
        # Add all the permissions
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        # Add some expenses created by the project owner
        ExpenseFactory.create_batch(2, owner=project.owner)

        response = graphql_query(
            self._project_with_owner_expenses_query(),
            variables={
                "id": project.id,
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        project_in_response = content["data"]["project"]
        assert project_in_response is not None
        assert project_in_response["id"] == str(project.id)
        # The owner and their expenses should show up, since the user has permission to
        # view both
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["id"] == str(project.owner.id)
        assert len(project_in_response["owner"]["expenses"]) == 2

    def test_nested_related_model_list_within_child_is_empty_without_permission_to_model(
        self, client: Client
    ):
        """
        Verify that we return a list as empty if the user does not have access to that
        model, even if that list is within a child's relations (nested deeper).
        """
        # Add all the permissions, except for expenses, and the list of expenses even
        # *within the project owner* field should end up empty
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        # Add some expenses created by the project owner
        ExpenseFactory.create_batch(2, owner=project.owner)

        response = graphql_query(
            self._project_with_owner_expenses_query(),
            variables={
                "id": project.id,
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        project_in_response = content["data"]["project"]
        assert project_in_response is not None
        assert project_in_response["id"] == str(project.id)
        # The owner should still show up, but its list of expenses should be empty since
        # the user does not have permission to view those
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["id"] == str(project.owner.id)
        assert len(project_in_response["owner"]["expenses"]) == 0

    def test_nonnullable_foreign_key_is_present_with_permission_to_model(
        self, client: Client
    ):
        """
        A non-nullable foreign key should show up (appear normal) if the user has
        permission to that model.
        """
        # The project owner is non-nullable, and it should show up fine since the user
        # has permission
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        expense = ExpenseFactory()

        response = graphql_query(
            self._expense_query(),
            variables={
                "id": expense.id,
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["id"] == str(expense.id)
        assert expense_in_response["amount"] == expense.amount
        assert expense_in_response["project"] is not None
        assert expense_in_response["project"]["id"] == str(expense.project.id)
        assert expense_in_response["project"]["owner"]["id"] == str(
            expense.project.owner.id
        )

    def test_nonnullable_foreign_key_raises_error_without_permission_to_model(
        self, client: Client
    ):
        """
        Since we can't circumvent the GraphQL schema at the authorization layer, if we
        come across a non-nullable field that the client has requested but for which the
        user doesn't have permission to the model, we should raise an error for that
        field.
        """
        # Exclude permission to the User, which is a non-nullable ForeignKey from
        # Project. This should raise an error, since the query is requesting the project
        # and owner data, but it's impossible to satisfy, given the requester's lack of
        # permission.
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
            ],
        )
        client.force_login(user)

        expense = ExpenseFactory()

        response = graphql_query(
            self._expense_query(),
            variables={
                "id": expense.id,
            },
            client=client,
        )

        # Verify that an error showed up for the expense's project owner (User), since
        # the user doesn't have permission
        assert_graphql_response_has_errors(response)
        content = json.loads(response.content)
        assert (
            "You do not have permission to access this field"
            in content["errors"][0]["message"]
        )
        assert content["errors"][0]["path"] == [
            "expense",
            "project",
            "owner",
        ]

        # The non-erroring data should still be returned
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["id"] == str(expense.id)
        assert expense_in_response["amount"] == expense.amount
        # The project should appear null (since it's a nullable field, so can be
        # omitted), as its owner couldn't be shown
        assert expense_in_response["project"] is None

    def test_nullable_foreign_key_is_present_with_permission_to_model(
        self, client: Client
    ):
        """
        A nullable foreign key should show up (appear normal) if the user has permission
        to that model.
        """
        # The Expense's project is nullable, and it should show up fine since the user
        # has permission
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        expense = ExpenseFactory(project=project)

        response = graphql_query(
            self._expense_query(),
            variables={
                "id": expense.id,
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["id"] == str(expense.id)
        assert expense_in_response["project"] is not None
        assert expense_in_response["project"]["id"] == str(project.id)

    def test_nullable_foreign_key_appears_empty_without_permission_to_model(
        self, client: Client
    ):
        """
        A nullable foreign key should appear null if the user does not have permission
        to that model (without error).
        """
        # The Expense's project (a nullable ForeignKey from Expense) should show up as
        # null if the user does not have permission to it
        user = UserFactory(
            permissions=[
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        expense = ExpenseFactory(project=project)
        assert expense.project is not None  # Sanity-check

        response = graphql_query(
            self._expense_query(),
            variables={
                "id": expense.id,
            },
            client=client,
        )

        # The project should show up as null, but there should be no errors in the
        # response, since we can safely omit it and still satisfy the GQL schema
        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["id"] == str(expense.id)
        assert expense_in_response["project"] is None

    def test_field_returning_list_instead_of_queryset_is_not_empty_with_permission(
        self, client: Client
    ):
        """
        If the user has permission to the main list-based returned model, it should show
        up in the results, but related queried sub-models should be omitted if not
        permitted.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(1, project=project2)

        response = graphql_query(
            self._projects_returning_list_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        # All of the projects should show up
        content = json.loads(response.content)
        projects_in_response = content["data"]["projectsList"]

        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        # The list of expenses should be empty for all projects, since the user doesn't
        # have permission to expenses, even though there is an expense for one of the
        # projects
        for project in projects_in_response:
            assert len(project["expenses"]) == 0

    def test_field_returning_list_instead_of_queryset_is_not_empty_with_permission_and_includes_allowed_sub_models(
        self, client: Client
    ):
        """
        If the user has permission to the main model as well as related queried
        sub-models, those should show up in the results.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(1, project=project2)

        response = graphql_query(
            self._projects_returning_list_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projectsList"]

        assert len(projects_in_response) == 2
        assert {project["id"] for project in projects_in_response} == {
            str(project1.id),
            str(project2.id),
        }

        # The list of expenses should be non-empty for the projects, since the user has
        # permission to view expenses
        for project in projects_in_response:
            assert len(project["expenses"]) > 0

    def test_field_returning_list_instead_of_queryset_is_empty_without_permission(
        self, client: Client
    ):
        user = UserFactory(
            permissions=[
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(1, project=project2)

        response = graphql_query(
            self._projects_returning_list_query(),
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        projects_in_response = content["data"]["projectsList"]

        # Since the user doesn't have permission to view projects, none should be
        # returned (even though this query resolver returns a list and not a QuerySet)
        assert len(projects_in_response) == 0

    def test_mutation_response_is_complete_with_permissions(self, client: Client):
        """
        When performing a mutation, the client's response should appear as normal if
        they have permission to all of the models.
        """
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        new_name = "New project name"
        response = graphql_query(
            self._project_mutation(),
            variables={
                "id": project.id,
                "input": {"name": new_name},
            },
            client=client,
        )

        # The mutation should've been performed successfully
        assert_graphql_response_has_no_errors(response)
        project.refresh_from_db()
        assert project.name == new_name

        # The response should contain all of the requested data, including the nested
        # user and expense data fields
        content = json.loads(response.content)
        project_in_response = content["data"]["projectUpdate"]["project"]
        assert project_in_response["id"] == str(project.id)
        assert project_in_response["name"] == new_name
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["id"] == str(project.owner.id)
        assert len(project_in_response["expenses"]) == 2
        assert project_in_response["expenses"][0]["owner"] is not None

    def test_mutation_response_omits_impermissible_data(self, client: Client):
        """
        When performing a mutation, if the client requests data in the response that
        they do not have access to, those should be omitted from the response.
        """
        # Omit the view permission for expenses
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        project = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project)

        new_name = "New project name"
        response = graphql_query(
            self._project_mutation(),
            variables={
                "id": project.id,
                "input": {"name": new_name},
            },
            client=client,
        )

        # The mutation itself should've been performed successfully, with no errors
        assert_graphql_response_has_no_errors(response)
        project.refresh_from_db()
        assert project.name == new_name

        # The response, however, should omit the unauthorized expenses data
        content = json.loads(response.content)
        project_in_response = content["data"]["projectUpdate"]["project"]
        assert project_in_response["id"] == str(project.id)
        assert project_in_response["name"] == new_name
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["id"] == str(project.owner.id)
        assert len(project_in_response["expenses"]) == 0

    def _assert_projects_with_expenses_sql_queries_match_expected(self, captured):
        """
        Validate that the SQL queries captured are what we expect, when querying for
        projects with nested expenses.
        """
        assert len(captured.captured_queries) == 6

        # Django should have queried for session- and user-data of the logged-in user
        assert re.match(
            r'SELECT .* FROM "django_session"', captured.captured_queries[0]["sql"]
        )
        assert re.match(
            r'SELECT .* FROM "auth_user"', captured.captured_queries[1]["sql"]
        )
        # Django should have fetched all of the user's permissions (their own and their
        # groups')
        assert re.match(
            r'SELECT .* FROM "auth_permission" INNER JOIN "auth_user_user_permissions"',
            captured.captured_queries[2]["sql"],
        )
        assert re.match(
            r'SELECT .* FROM "auth_permission" INNER JOIN "auth_group_permissions"',
            captured.captured_queries[3]["sql"],
        )

        # We should have queried for all projects, joined with users for the owner data,
        # using a single query
        assert re.match(
            r'SELECT .* FROM "tests_project" INNER JOIN "auth_user"',
            captured.captured_queries[4]["sql"],
        )

        # We should have queried for all of the expenses of all of the projects, joined
        # with users for the expense owner data, using a single query
        assert re.match(
            r'SELECT .* FROM "tests_expense" INNER JOIN "auth_user"',
            captured.captured_queries[5]["sql"],
        )

    def test_sql_queries_are_still_optimized_when_user_has_permissions(
        self, client: Client, django_assert_num_queries
    ):
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "tests.view_expense",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)

        with django_assert_num_queries(6) as captured:
            response = graphql_query(
                query=self._projects_with_expenses_query(),
                client=client,
            )

        # Sanity-check that the response was valid
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]
        assert len(projects_in_response) == 2
        assert len(projects_in_response[0]["expenses"]) > 0

        self._assert_projects_with_expenses_sql_queries_match_expected(captured)

    def test_sql_queries_are_still_optimized_when_user_is_missing_permissions(
        self, client: Client, django_assert_num_queries
    ):
        # Omit permission to view expenses, which should remove them from the response
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)

        # The query-performance should be the same as it was when the user had all
        # permissions. Gating the expenses should incur no additional SQL hit.
        with django_assert_num_queries(6) as captured:
            response = graphql_query(
                query=self._projects_with_expenses_query(),
                client=client,
            )

        # Sanity-check that the response was valid
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]
        assert len(projects_in_response) == 2
        # Expenses should be empty since the user does not have permission to view them
        assert len(projects_in_response[0]["expenses"]) == 0

        # The SQL query performance should be the same as when a user has all
        # permission, still optimized
        self._assert_projects_with_expenses_sql_queries_match_expected(captured)

    @pytest.mark.usefixtures("use_owner_permitted_auth_backend")
    def test_sql_queries_are_still_optimized_when_using_object_level_permissions(
        self, client: Client, django_assert_num_queries
    ):
        # Omit permission to view all expenses, which should restrict the ones shown to
        # those that the user owns
        user = UserFactory(
            permissions=[
                "tests.view_project",
                "auth.view_user",
            ],
        )
        client.force_login(user)

        # Create a couple projects and add expenses to them, including some owned by the
        # requesting user
        project1 = ProjectFactory()
        ExpenseFactory.create_batch(3, project=project1)
        ExpenseFactory.create_batch(2, project=project1, owner=user)
        project2 = ProjectFactory()
        ExpenseFactory.create_batch(2, project=project2)
        ExpenseFactory.create_batch(2, project=project2, owner=user)

        # The query-performance should be the same as it was when the user had all
        # model-level sweeping permissions, since the authorization backend doesn't
        # require any additional queries.
        with django_assert_num_queries(6) as captured:
            response = graphql_query(
                query=self._projects_with_expenses_query(),
                client=client,
            )

        # Sanity-check that the response was valid
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        projects_in_response = content["data"]["projects"]
        assert len(projects_in_response) == 2
        # Expenses should contain only the ones owned by the user
        assert len(projects_in_response[0]["expenses"]) == 2
        assert len(projects_in_response[1]["expenses"]) == 2

        # The SQL query performance should be the same as when a user has all
        # permission, still optimized
        self._assert_projects_with_expenses_sql_queries_match_expected(captured)
