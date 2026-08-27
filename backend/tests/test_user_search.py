import pytest
from fastapi.testclient import TestClient

from app.db import db
from app.main import app

client = TestClient(app)

TEST_USERS = [
    {"name": "Search Owner", "email": "search.owner@example.com", "password": "Password123"},
    {"name": "Search User Two", "email": "usertwo.search@example.com", "password": "Password123"},
    {"name": "Search User Three", "email": "userthree.search@example.com", "password": "Password123"},
    {"name": "An Other Person", "email": "another.search@example.com", "password": "Password123"},
]


@pytest.fixture(autouse=True)
def cleanup_test_users():
    emails = [user["email"] for user in TEST_USERS]
    collection = db.get_db()["users"]
    collection.delete_many({"email": {"$in": emails}})
    yield
    collection.delete_many({"email": {"$in": emails}})


def register_and_login(user):
    client.post("/auth/register", json=user)
    response = client.post(
        "/auth/login",
        json={"email": user["email"], "password": user["password"]},
    )
    return response.json()["access_token"]


def test_authenticated_user_can_search_by_name_and_excludes_themselves():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])

    response = client.get("/users/search?q=Search User Two", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    users = response.json()["users"]
    assert [user["email"] for user in users] == [TEST_USERS[1]["email"]]
    assert all("password" not in user and "password_hash" not in user for user in users)


def test_search_by_partial_email_is_case_insensitive():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])

    response = client.get(
        "/users/search?q=USERtwo.SEARCH",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["users"][0]["email"] == TEST_USERS[1]["email"]


def test_partial_name_search_returns_multiple_matches():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[1])
    register_and_login(TEST_USERS[2])

    response = client.get("/users/search?q=Search User", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert {user["email"] for user in response.json()["users"]} == {
        TEST_USERS[1]["email"],
        TEST_USERS[2]["email"],
    }


def test_no_matching_users_returns_empty_list():
    token = register_and_login(TEST_USERS[0])

    response = client.get(
        "/users/search?q=does-not-exist",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"users": []}


@pytest.mark.parametrize("query", ["", "   "])
def test_empty_or_whitespace_query_is_rejected(query):
    token = register_and_login(TEST_USERS[0])

    response = client.get(
        "/users/search",
        params={"q": query},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_missing_query_is_rejected():
    token = register_and_login(TEST_USERS[0])

    response = client.get("/users/search", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 422


def test_excessively_long_query_is_rejected():
    token = register_and_login(TEST_USERS[0])

    response = client.get(
        "/users/search",
        params={"q": "a" * 101},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_search_requires_authentication():
    response = client.get("/users/search?q=User")

    assert response.status_code == 401


def test_invalid_token_is_rejected():
    response = client.get(
        "/users/search?q=User",
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )

    assert response.status_code == 401


def test_response_contains_only_public_user_fields():
    token = register_and_login(TEST_USERS[0])
    register_and_login(TEST_USERS[3])

    response = client.get(
        "/users/search?q=another",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    users = response.json()["users"]
    assert len(users) == 1
    assert set(users[0]) == {"id", "name", "email"}
    assert "_id" not in users[0]
    assert "password_hash" not in users[0]
    assert users[0]["email"] == TEST_USERS[3]["email"]
