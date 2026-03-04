# -*- coding: utf-8 -*-
{
    "name": "Módulo de Inteligencia y Análisis de Compras Odoo 19",
    "summary": """
        Transforme su departamento de compras en una potencia proactiva basada en datos.
        Asegura CERO ROTURAS DE STOCK mediante previsión inteligente y reordenamiento automatizado.
    """,
    "description": """
        Módulo de Inteligencia y Análisis de Compras Odoo 19
        ====================================================

        Basado en la Versión 2.0 - Especificación Edición Enterprise.

        Características Principales:
        - Sistema Central de Tableros (Ejecutivo, Operativo, Táctico)
        - Centro de Inteligencia de Inventario (Movimiento de Productos, Niveles de Stock, ABC-XYZ)
        - Marco Completo de KPI (Financiero, Operativo, Calidad, Inventario, Proveedores, Cumplimiento)
        - Gestión del Rendimiento de Proveedores (Cuadros de Mando, Segmentación, Riesgos)
        - Análisis de Precios y Previsión (Comportamiento, Inteligencia de Mercado, Ahorros)
        - Sistema de Reordenamiento Automatizado (ROP Dinámico, Reglas de Flujo, EOQ)
        - Gestión de Acuerdos de Compra
        - Sistema de Clasificación de Productos (FSN, VED)
        - Gestión de Riesgos y Alertas
        - Suite de Informes y Análisis
    """,
    "author": "Su Compañía",
    "website": "http://www.sucompania.com",
    "category": "Inventory/Purchase",
    "version": "19.0.2.0.0",
    "license": "OPL-1",
    "depends": [
        "base",
        "purchase",
        "stock",
        "account",
        "sale_management",
        "mrp",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/sequences.xml",
        "data/kpi_data.xml",
        "data/alert_data.xml",
        "data/cron.xml",
        "views/root_menus.xml",
        "views/dashboard_actions.xml",
        "views/kpi_views.xml",
        "views/alert_views.xml",
        "views/analysis_views.xml",
        "views/supplier_views.xml",
        "views/product_views.xml",
        "views/purchase_views.xml",
        "views/savings_views.xml",
        "views/contract_views.xml",
        "views/automated_orders_views.xml",
        "views/price_history_views.xml",
        "views/risk_forecast_views.xml",
        "views/warehouse_reorder_views.xml",
        "views/pi_reorder_command_views.xml",
        "views/warehouse_comparison_views.xml",
        "reports/purchase_intelligence_report.xml",
        "reports/advanced_reports.xml",
        "views/config_views.xml",
        "views/stock_warehouse_views.xml",
        "views/menus.xml",
        "views/stockout_prevention_views.xml",
        "views/smart_transfer_views.xml",
        "views/warehouse_views.xml",
        "views/visual_intelligence_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "Purchase_advance_astra/static/src/scss/dashboard.scss",
            "Purchase_advance_astra/static/src/scss/visual_widgets.scss",
            "Purchase_advance_astra/static/src/js/dashboards/master_dashboard.js",
            "Purchase_advance_astra/static/src/js/dashboards/inventory_dashboard.js",
            "Purchase_advance_astra/static/src/js/dashboards/supplier_dashboard.js",
            "Purchase_advance_astra/static/src/js/widgets/intelligence_card.js",
            "Purchase_advance_astra/static/src/xml/master_dashboard.xml",
            "Purchase_advance_astra/static/src/xml/inventory_dashboard.xml",
            "Purchase_advance_astra/static/src/xml/supplier_dashboard.xml",
            "Purchase_advance_astra/static/src/xml/widgets/intelligence_widgets.xml",
        ],
    },
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "post_init_hook",
}
