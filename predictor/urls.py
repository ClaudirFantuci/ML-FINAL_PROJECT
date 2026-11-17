from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("api/pontos/", views.pontos, name="pontos"),
    path("api/estimar/", views.estimar, name="estimar"),
]
