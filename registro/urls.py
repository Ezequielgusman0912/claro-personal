from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("movimientos/", views.dashboard, name="movements"),
    path("demo/", views.demo, name="demo"),
    path("nuevo/", views.new_movement, name="new"),
    path("comprobantes/extraer-datos/", views.extract_receipt_data, name="extract_receipt_data"),
    path("movimientos/<int:pk>/", views.movement_detail, name="movement_detail"),
    path("movimientos/<int:pk>/editar/", views.edit_movement, name="edit"),
    path("movimientos/<int:pk>/eliminar/", views.delete_movement, name="delete_movement"),
    path("movimientos/<int:pk>/comprobante/", views.receipt, name="receipt"),
    path("movimientos/<int:pk>/leer/", views.retry_extraction, name="retry_extraction"),
    path("cuentas/", views.accounts, name="accounts"),
    path("exportar/", views.export, name="export"),
]
