import factory
from django.contrib.auth.models import User

from tests.models import Expense, Project
from tests.utils import add_permissions_for_user


class UserFactory(factory.django.DjangoModelFactory):
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    username = factory.Sequence(lambda n: "username%d" % n)

    class Meta:
        model = User

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if not create:
            return

        if not extracted:
            return

        add_permissions_for_user(self, extracted)


class ProjectFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("sentence")
    owner = factory.SubFactory(UserFactory)

    class Meta:
        model = Project


class ExpenseFactory(factory.django.DjangoModelFactory):
    owner = factory.SubFactory(UserFactory)
    project = factory.SubFactory(ProjectFactory)
    amount = factory.Faker("pyint")

    class Meta:
        model = Expense
