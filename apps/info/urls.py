from django.urls import path
from . import views

app_name = 'info'

urlpatterns = [
    path('health/<slug:slug>/', views.health_list, name='health_list'),
    path('health/<slug:slug>/new/', views.health_create, name='health_create'),
    path('health/<slug:slug>/<int:pk>/edit/', views.health_edit, name='health_edit'),
    path('health/<slug:slug>/<int:pk>/delete/', views.health_delete, name='health_delete'),
    path('health/<slug:slug>/<int:pk>/status/', views.health_status, name='health_status'),
    path('', views.info_list_page, name='info_list'),
    path('ajax/list/', views.info_list_ajax, name='info_list_ajax'),
    path('ajax/get/<int:pk>/', views.info_get_ajax, name='info_get_ajax'),
    path('ajax/save/', views.info_save_ajax, name='info_save_ajax'),
    path('ajax/delete/<int:pk>/', views.info_delete_ajax, name='info_delete_ajax'),
]
