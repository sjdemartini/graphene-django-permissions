import json
from functools import partial

import pytest
from django.test.client import Client
from graphene_django.utils.testing import graphql_query as graphql_query_original
from graphql_relay import to_global_id

from tests.factories import ExpenseFactory, ProjectFactory, UserFactory
from tests.utils import (
    assert_graphql_response_has_errors,
    assert_graphql_response_has_no_errors,
)

pytestmark = pytest.mark.django_db

# For all of the tests below, we'll route them to our relay-based GraphQL view/schema
GRAPHQL_RELAY_URL = "/graphql-relay/"  # See urls.py
graphql_query = partial(graphql_query_original, graphql_url=GRAPHQL_RELAY_URL)


class TestGrapheneAuthorizationMiddlewareWithRelaySchema:
    """
    Test that the Graphene authorization middleware properly restricts read access
    depending on user permissions, when using a relay-based GQL schema.
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
                        edges {
                            node {
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
            }
        """

    def _projects_with_expenses_query(self):
        return """
            query ProjectsQuery {
                projects {
                    edges {
                        node {
                            id
                            name

                            owner {
                                id
                                username
                            }

                            expenses {
                                edges {
                                    node {
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
                            edges {
                                node {
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
        projects_in_response = content["data"]["projects"]["edges"]

        # All of the projects and expenses should be visible, with their associated user
        # data
        assert len(projects_in_response) == 2
        assert {
            project_node["node"]["name"] for project_node in projects_in_response
        } == {
            project1.name,
            project2.name,
        }

        project1_in_response = next(
            project["node"]
            for project in projects_in_response
            if project["node"]["name"] == project1.name
        )
        assert project1_in_response["owner"] is not None
        assert len(project1_in_response["expenses"]["edges"]) == 5
        assert project1_in_response["expenses"]["edges"][0]["node"]["owner"] is not None

        project2_in_response = next(
            project["node"]
            for project in projects_in_response
            if project["node"]["name"] == project2.name
        )
        assert project2_in_response["owner"] is not None
        assert project2_in_response["expenses"]["edges"][0]["node"]["owner"] is not None

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
        ProjectFactory()

        response = graphql_query(
            self._projects_with_expenses_query(),
            client=client,
        )

        # There should be no errors, but the top-level list should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        assert len(content["data"]["projects"]["edges"]) == 0

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
                "id": to_global_id("ProjectNode", project.id),
            },
            client=client,
        )

        # There should be no errors, but the top-level object should be empty
        assert_graphql_response_has_no_errors(response)
        content = json.loads(response.content)
        project_in_response = content["data"]["project"]
        assert project_in_response is not None
        assert project_in_response["name"] == project.name
        assert project_in_response["owner"] is not None
        assert len(project_in_response["expenses"]["edges"]) == 2
        assert project_in_response["expenses"]["edges"][0]["node"]["owner"] is not None

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
                "id": to_global_id("ProjectNode", project.id),
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
        projects_in_response = content["data"]["projects"]["edges"]

        # The projects should show up, but expenses should be empty
        assert len(projects_in_response) == 2
        assert {
            project_node["node"]["name"] for project_node in projects_in_response
        } == {
            project1.name,
            project2.name,
        }

        assert len(projects_in_response[0]["node"]["expenses"]["edges"]) == 0
        assert len(projects_in_response[1]["node"]["expenses"]["edges"]) == 0

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
                "id": to_global_id("ProjectNode", project.id),
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
        assert project_in_response["name"] == new_name
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["username"] == project.owner.username
        assert len(project_in_response["expenses"]["edges"]) == 2
        assert project_in_response["expenses"]["edges"][0]["node"]["owner"] is not None

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
                "id": to_global_id("ProjectNode", project.id),
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
        assert project_in_response["name"] == new_name
        assert project_in_response["owner"] is not None
        assert project_in_response["owner"]["username"] == project.owner.username
        assert len(project_in_response["expenses"]["edges"]) == 0

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
                "id": to_global_id("ExpenseNode", expense.id),
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["amount"] == expense.amount
        assert expense_in_response["project"] is not None
        assert expense_in_response["project"]["name"] == expense.project.name
        assert expense_in_response["project"]["owner"]["username"] == str(
            expense.project.owner.username
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
                "id": to_global_id("ExpenseNode", expense.id),
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
                "id": to_global_id("ExpenseNode", expense.id),
            },
            client=client,
        )

        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["amount"] == expense.amount
        assert expense_in_response["project"] is not None
        assert expense_in_response["project"]["name"] == project.name

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
                "id": to_global_id("ExpenseNode", expense.id),
            },
            client=client,
        )

        # The project should show up as null, but there should be no errors in the
        # response, since we can safely omit it and still satisfy the GQL schema
        assert_graphql_response_has_no_errors(response)

        content = json.loads(response.content)
        expense_in_response = content["data"]["expense"]
        assert expense_in_response["amount"] == expense.amount
        assert expense_in_response["project"] is None
