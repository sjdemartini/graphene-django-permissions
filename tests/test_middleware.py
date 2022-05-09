import json

import pytest
from django.test.client import Client
from graphene_django.utils.testing import graphql_query

from tests.factories import ExpenseFactory, ProjectFactory, UserFactory
from tests.utils import assert_graphql_response_has_no_errors

pytestmark = pytest.mark.django_db


class TestGrapheneAuthorizationMiddleware:
    """
    Test that the Graphene authorization middleware properly restricts read access
    depending on user permissions.
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

                        creator {
                            id
                            username
                        }
                    }
                }
            }
        """

    def test_all_data_returned_when_have_all_permissions(self, client: Client):
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
        assert len(project1_in_response["expenses"]) == 5

        project2_in_response = next(
            project
            for project in projects_in_response
            if project["id"] == str(project2.id)
        )
        assert len(project2_in_response["expenses"]) == 2

    def test_nested_related_model_list_empty_when_missing_permissions(
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
