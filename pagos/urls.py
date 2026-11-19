from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("ingresar/", auth_views.LoginView.as_view(
        template_name="registro/login.html"
    ), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("registro.urls")),
]
