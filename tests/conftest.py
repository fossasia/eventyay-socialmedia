import pytest
from eventyay.base.models import Event, Organizer, Team, User
from django.utils.timezone import now
from datetime import timedelta


@pytest.fixture
def organizer():
    return Organizer.objects.create(name="Test Organizer", slug="test-org")


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="test-event",
        date_from=now(),
        date_to=now() + timedelta(days=1),
        currency="USD",
        live=True,
        plugins="socialmedia",
    )


@pytest.fixture
def user():
    return User.objects.create_user("dummy@dummy.dummy", "dummy")


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def logged_in_organizer_client(client, user, organizer, event):
    team = Team.objects.create(
        organizer=organizer,
        name="Test Team",
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(user)
    client.force_login(user)
    return client
