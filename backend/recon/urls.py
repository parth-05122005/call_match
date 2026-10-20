from django.urls import path
from recon import views

# All paths below start with /api/ 
urlpatterns = [
    path("organizations/", views.list_organizations),
    path("transactions/", views.list_transactions),
    path("transactions/import/", views.import_transactions),
    path("transactions/<int:transaction_id>/ignore/", views.ignore_transaction),
    path("line-items/", views.list_line_items),
    path("matches/<int:match_id>/approve/", views.approve_match),
    path("matches/<int:match_id>/reject/", views.reject_match),
]