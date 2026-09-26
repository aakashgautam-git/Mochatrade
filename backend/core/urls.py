"""Routes under /api/."""
from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("policies/", views.PolicyListView.as_view(), name="policies"),
    path("policies/recalibrate/", views.PolicyRecalibrateView.as_view(), name="policies-recalibrate"),
    path("instruments/", views.InstrumentListView.as_view(), name="instruments"),
    path("scenarios/", views.ScenarioListView.as_view(), name="scenarios"),
    path("scenarios/<slug:slug>/", views.ScenarioDetailView.as_view(), name="scenario-detail"),

    path("runs/", views.RunCreateView.as_view(), name="runs"),
    path("runs/compare/", views.RunCompareView.as_view(), name="runs-compare"),

    # The screening-round demo. Byte-compatible alias over the new implementation.
    path("compare/<slug:slug>/", views.LegacyCompareView.as_view(), name="compare"),

    path("incidents/", views.IncidentCreateView.as_view(), name="incidents"),
    path("incidents/<str:code>/state/", views.IncidentStateView.as_view(), name="incident-state"),
    path("incidents/<str:code>/step/", views.IncidentStepView.as_view(), name="incident-step"),
    path("incidents/<str:code>/clock/", views.IncidentClockView.as_view(), name="incident-clock"),
    path("incidents/<str:code>/ticks/", views.IncidentTicksView.as_view(), name="incident-ticks"),
    path("incidents/<str:code>/action/", views.IncidentActionView.as_view(), name="incident-action"),
    path("incidents/<str:code>/classify/", views.IncidentClassifyView.as_view(), name="incident-classify"),
    path("incidents/<str:code>/evidence/", views.IncidentEvidenceView.as_view(), name="incident-evidence"),
    path("incidents/<str:code>/claims/", views.IncidentClaimsView.as_view(), name="incident-claims"),
    path(
        "incidents/<str:code>/claims/<int:claim_id>/decide/",
        views.ClaimDecideView.as_view(),
        name="claim-decide",
    ),
    path("incidents/<str:code>/comms/", views.IncidentCommsView.as_view(), name="incident-comms"),
    path("incidents/<str:code>/report/", views.IncidentReportView.as_view(), name="incident-report"),

    path("status/", views.PublicStatusView.as_view(), name="public-status"),
]
