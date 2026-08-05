from unittest.mock import patch

import pytest

from blog.forms import MODERATION_ERROR, CommentForm
from blog.models import Comment
from blog.moderation import is_toxic
from core.constants import TOXICITY_THRESHOLD


def test_toxicity_threshold_is_configured():
    assert TOXICITY_THRESHOLD == 0.8


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (TOXICITY_THRESHOLD - 0.01, False),
        (TOXICITY_THRESHOLD, True),
    ],
)
def test_is_toxic_uses_configured_threshold(score, expected):
    with patch("blog.moderation.get_toxicity_score", return_value=score):
        assert is_toxic("Текст для проверки") is expected


def test_comment_form_accepts_neutral_text_without_loading_model():
    with patch("blog.forms.is_toxic", return_value=False):
        form = CommentForm(data={"text": "Спасибо за полезную публикацию!"})
        assert form.is_valid()


def test_comment_form_rejects_toxic_text_without_loading_model():
    with patch("blog.forms.is_toxic", return_value=True):
        form = CommentForm(data={"text": "Токсичный текст"})
        assert not form.is_valid()

    assert MODERATION_ERROR in form.errors["text"]


@pytest.mark.django_db
def test_toxic_comment_is_not_created_and_error_is_displayed(
    post_with_published_location,
    user_client,
):
    create_url = (
        f"/posts/{post_with_published_location.pk}/comment/"
    )

    with patch("blog.forms.is_toxic", return_value=True):
        response = user_client.post(
            create_url,
            {"text": "Токсичный текст"},
        )

    assert response.status_code == 200
    assert not Comment.objects.filter(
        post=post_with_published_location,
    ).exists()
    assert MODERATION_ERROR in response.content.decode()


@pytest.mark.django_db
def test_neutral_comment_is_created(
    post_with_published_location,
    user,
    user_client,
):
    create_url = (
        f"/posts/{post_with_published_location.pk}/comment/"
    )

    with patch("blog.forms.is_toxic", return_value=False):
        response = user_client.post(
            create_url,
            {"text": "Корректный комментарий"},
        )

    assert response.status_code == 302
    assert Comment.objects.filter(
        post=post_with_published_location,
        author=user,
        text="Корректный комментарий",
    ).exists()


@pytest.mark.django_db
def test_toxic_edit_does_not_change_comment(
    post_with_published_location,
    user,
    user_client,
):
    original_text = "Исходный корректный комментарий"
    comment = Comment.objects.create(
        post=post_with_published_location,
        author=user,
        text=original_text,
    )
    edit_url = (
        f"/posts/{post_with_published_location.pk}/"
        f"edit_comment/{comment.pk}/"
    )

    with patch("blog.forms.is_toxic", return_value=True):
        response = user_client.post(
            edit_url,
            {"text": "Токсичная новая версия"},
        )

    comment.refresh_from_db()
    assert response.status_code == 200
    assert comment.text == original_text
    assert MODERATION_ERROR in response.content.decode()
