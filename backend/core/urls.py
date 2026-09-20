"""Routes under /api/."""
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("scenarios/", views.scenarios, name="scenarios"),
    path("compare/<slug:slug>/", views.compare, name="compare"),
]
