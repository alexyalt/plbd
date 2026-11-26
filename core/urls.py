from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.dashboard, name="dashboard"),
    path("catalogs/", v.catalogs, name="catalogs"),
    path("catalog/<slug:slug>/", v.catalog_list, name="catalog_list"),
    path("catalog/<slug:slug>/new/", v.catalog_edit, name="catalog_new"),
    path("catalog/<slug:slug>/<int:pk>/", v.catalog_edit, name="catalog_edit"),
    path("catalog/<slug:slug>/<int:pk>/delete/", v.catalog_delete, name="catalog_delete"),
    path("inspections/", v.inspection_list, name="inspection_list"),
    path("inspections/new/", v.inspection_edit, name="inspection_new"),
    path("inspections/<int:pk>/", v.inspection_detail, name="inspection_detail"),
    path("inspections/<int:pk>/edit/", v.inspection_edit, name="inspection_edit"),
    path("inspections/<int:pk>/done/", v.inspection_done, name="inspection_done"),
    path("inspections/<int:pk>/delete/", v.inspection_delete, name="inspection_delete"),
    path("treatments/", v.treatment_list, name="treatment_list"),
    path("treatments/new/", v.treatment_edit, name="treatment_new"),
    path("treatments/<int:pk>/edit/", v.treatment_edit, name="treatment_edit"),
    path("treatments/<int:pk>/delete/", v.treatment_delete, name="treatment_delete"),
    path("writeoff/", v.writeoff, name="writeoff"),
    path("writeoff/confirm/", v.writeoff_confirm, name="writeoff_confirm"),
    path("protection/", v.protection, name="protection"),
    path("reports/", v.reports_page, name="reports"),
    path("reports/inspections.xlsx", v.report_inspections, name="report_inspections"),
    path("reports/journal.xlsx", v.report_journal, name="report_journal"),
    path("reports/treatments.xlsx", v.report_treatments, name="report_treatments"),
    path("duplicates/", v.duplicates, name="duplicates"),
    path("tools/", v.tools, name="tools"),
    path("tools/backup/", v.backup, name="backup"),
    path("tools/migration-report/", v.migration_report, name="migration_report"),
    path("tools/audit/", v.audit_log, name="audit"),
]
