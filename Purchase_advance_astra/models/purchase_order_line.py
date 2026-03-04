# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    # === INFORMACIÓN DE VENTAS (calculada automáticamente) ===
    astra_product_image = fields.Binary(
        string="Imagen", related="product_id.image_128", readonly=True
    )

    sales_last_week = fields.Float(
        string="Ventas Última Semana",
        compute="_compute_sales_history",
        help="Cantidad vendida en los últimos 7 días",
    )
    sales_last_month = fields.Float(
        string="Ventas Último Mes",
        compute="_compute_sales_history",
        help="Cantidad vendida en los últimos 30 días",
    )
    sales_last_3_months = fields.Float(
        string="Ventas 3 Meses",
        compute="_compute_sales_history",
        help="Cantidad vendida en los últimos 90 días",
    )
    sales_last_6_months = fields.Float(
        string="Ventas 6 Meses",
        compute="_compute_sales_history",
        help="Cantidad vendida en los últimos 180 días",
    )
    avg_daily_sales = fields.Float(
        string="Venta Diaria Promedio",
        compute="_compute_sales_history",
        help="Promedio de ventas diarias (basado en 90 días)",
    )

    # === INFORMACIÓN DE STOCK ===
    current_stock = fields.Float(
        string="Stock Actual", related="product_id.qty_available", readonly=True
    )
    stock_coverage_days = fields.Float(
        string="Días de Cobertura",
        compute="_compute_stock_coverage",
        help="Cuántos días durará el stock actual más lo pedido",
    )
    virtual_available = fields.Float(
        string="Stock Virtual", related="product_id.virtual_available", readonly=True
    )
    stock_by_warehouse = fields.Html(
        string="Stock por Almacén",
        compute="_compute_stock_by_warehouse",
        help="Detalle de existencias por cada almacén",
    )

    # === ÚLTIMA COMPRA ===
    last_purchase_date = fields.Date(
        string="Última Compra",
        compute="_compute_last_purchase",
        help="Fecha de la última orden de compra de este producto",
    )
    last_purchase_price = fields.Float(
        string="Precio Última Compra",
        compute="_compute_last_purchase",
        help="Precio unitario de la última compra",
    )
    last_purchase_qty = fields.Float(
        string="Cant. Última Compra",
        compute="_compute_last_purchase",
    )
    # Campos de historial de precios (de purchase_history module)
    last_price1 = fields.Float(
        string="UPDC 1",
        help="Último precio de compra del producto para el proveedor seleccionado",
        readonly=True,
        store=False,
    )
    last_price2 = fields.Float(
        string="UPDC 2",
        help="Penúltimo precio de compra del producto para el proveedor seleccionado",
        readonly=True,
        store=False,
    )
    warehouse_quantity_html = fields.Html(
        string="Existencia Almacén",
        compute="_compute_warehouse_quantity_html",
        readonly=True,
        store=False,
    )
    last_supplier = fields.Char(
        string="Último Proveedor",
        compute="_compute_last_purchase",
    )
    days_since_purchase = fields.Integer(
        string="Días Sin Comprar",
        compute="_compute_last_purchase",
    )

    # === COMPARACIÓN DE PRECIOS ===
    price_variation = fields.Float(
        string="Variación Precio %",
        compute="_compute_price_comparison",
        help="Variación respecto al precio anterior",
    )
    price_trend = fields.Selection(
        [("up", "↑ Subió"), ("down", "↓ Bajó"), ("stable", "→ Estable")],
        string="Tendencia Precio",
        compute="_compute_price_comparison",
    )

    standard_price = fields.Float(
        string="Costo Estándar", related="product_id.standard_price", readonly=True
    )
    margin_vs_standard = fields.Float(
        string="Margen vs Estándar %",
        compute="_compute_price_comparison",
        help="Diferencia % entre precio de compra y costo estándar",
    )

    # === INDICADORES DE ROTACIÓN ===
    product_abc = fields.Selection(
        related="product_id.product_tmpl_id.abc_classification",
        string="Clasificación ABC",
        readonly=True,
    )
    product_fsn = fields.Selection(
        related="product_id.product_tmpl_id.fsn_classification",
        string="Velocidad (FSN)",
        readonly=True,
    )

    # === RECOMENDACIONES ===
    qty_recommendation = fields.Float(
        string="Cantidad Recomendada",
        compute="_compute_recommendation",
        help="Cantidad sugerida basada en análisis de ventas",
    )
    recommendation_reason = fields.Char(
        string="Razón Sugerencia",
        compute="_compute_recommendation",
    )

    # === PIPELINE DE VENTAS PENDIENTES (NUEVO) ===
    pending_quotations_qty = fields.Float(
        string="Qty en Cotizaciones",
        compute="_compute_sales_pipeline",
        help="Cantidad en cotizaciones pendientes de confirmar",
    )
    pending_quotations_count = fields.Integer(
        string="# Cotizaciones",
        compute="_compute_sales_pipeline",
        help="Número de cotizaciones pendientes con este producto",
    )
    confirmed_undelivered_qty = fields.Float(
        string="Qty Confirmada Sin Entregar",
        compute="_compute_sales_pipeline",
        help="Cantidad en órdenes confirmadas pendientes de entrega",
    )
    confirmed_undelivered_count = fields.Integer(
        string="# Órdenes Sin Entregar",
        compute="_compute_sales_pipeline",
        help="Número de órdenes confirmadas sin entregar completamente",
    )
    total_sales_pipeline = fields.Float(
        string="Total Pipeline Ventas",
        compute="_compute_sales_pipeline",
        help="Total de demanda pendiente (cotizaciones + confirmadas)",
    )

    # === RIESGO DE VENTAS PERDIDAS ===
    lost_sales_risk_qty = fields.Float(
        string="Riesgo Ventas Perdidas (Qty)",
        compute="_compute_lost_sales_risk",
        help="Cantidad de la demanda del pipeline que no se podrá cubrir con stock actual",
    )
    lost_sales_risk_amount = fields.Monetary(
        string="Riesgo Ventas Perdidas ($)",
        compute="_compute_lost_sales_risk",
        currency_field="currency_id",
        help="Valor monetario de las ventas que se podrían perder",
    )
    projected_stockout_date = fields.Date(
        string="Fecha de Agotamiento",
        compute="_compute_lost_sales_risk",
        help="Fecha proyectada en la que se agotará el stock",
    )
    currency_id = fields.Many2one(
        "res.currency", related="order_id.currency_id", readonly=True
    )

    # === INTELIGENCIA DE ALMACENES ===
    warehouse_intelligence_ids = fields.Many2many(
        "pi.product.warehouse.intelligence",
        string="Warehouse Intelligence",
        compute="_compute_warehouse_intelligence_ids",
        store=False,
    )

    # === DIMENSIONES Y PESO ===
    weight = fields.Float(
        string="Peso Unitario", related="product_id.weight", readonly=True
    )
    volume = fields.Float(
        string="Volumen Unitario", related="product_id.volume", readonly=True
    )
    total_weight = fields.Float(
        string="Peso Total", compute="_compute_weight_volume", store=True
    )
    total_volume = fields.Float(
        string="Volumen Total", compute="_compute_weight_volume", store=True
    )

    @api.depends("product_qty", "product_id.weight", "product_id.volume")
    def _compute_weight_volume(self):
        for line in self:
            line.total_weight = (line.product_id.weight or 0.0) * line.product_qty
            line.total_volume = (line.product_id.volume or 0.0) * line.product_qty

    def _compute_warehouse_quantity_html(self):
        """Compute warehouse quantity for each line"""
        for line in self:
            if not line.product_id:
                line.warehouse_quantity_html = (
                    '<span style="color: #888;">Sin producto</span>'
                )
                continue

            warehouses = self.env["stock.warehouse"].search([])
            if not warehouses:
                line.warehouse_quantity_html = (
                    '<span style="color: #888;">Sin almacenes</span>'
                )
                continue

            html_parts = []
            for warehouse in warehouses:
                qty = sum(
                    self.env["stock.quant"]
                    .search(
                        [
                            ("product_id", "=", line.product_id.id),
                            ("location_id", "child_of", warehouse.lot_stock_id.id),
                        ]
                    )
                    .mapped("quantity")
                )

                if qty <= 0:
                    color = "#dc3545"
                    icon = "⚠️"
                elif qty < 10:
                    color = "#fd7e14"
                    icon = "⚡"
                else:
                    color = "#28a745"
                    icon = "✅"

                html_parts.append(
                    f'<span style="color: {color};">{icon} {warehouse.name}: {int(qty)}</span> '
                )

            line.warehouse_quantity_html = (
                "".join(html_parts)
                if html_parts
                else '<span style="color: #888;">Sin datos</span>'
            )

    def action_open_intelligence(self):
        """Abrir popup con la inteligencia detallada"""
        self.ensure_one()
        view_id = self.env.ref(
            "Purchase_advance_astra.view_purchase_order_line_intelligence_form"
        ).id
        return {
            "name": f"Inteligencia de Stock: {self.product_id.name}",
            "type": "ir.actions.act_window",
            "view_mode": "form",
            "res_model": "purchase.order.line",
            "res_id": self.id,
            "view_id": view_id,
            "target": "new",
            "flags": {"mode": "readonly"},
        }

    def _compute_warehouse_intelligence_ids(self):
        """Compute warehouse intelligence from product template"""
        for line in self:
            if line.product_id and line.product_id.product_tmpl_id:
                # Filter only active warehouses
                line.warehouse_intelligence_ids = (
                    line.product_id.product_tmpl_id.warehouse_intelligence_ids.filtered(
                        lambda r: r.warehouse_id.active_intelligence
                    )
                )
            else:
                line.warehouse_intelligence_ids = False

    def _compute_sales_history(self):
        """Calcular historial de ventas del producto desde stock.move"""
        today = fields.Date.context_today(self)

        for line in self:
            if not line.product_id:
                line.sales_last_week = 0
                line.sales_last_month = 0
                line.sales_last_3_months = 0
                line.sales_last_6_months = 0
                line.avg_daily_sales = 0
                continue

            # Buscar movimientos de salida (ventas)
            StockMove = self.env["stock.move"]
            base_domain = [
                ("product_id", "=", line.product_id.id),
                ("state", "=", "done"),
                ("location_id.usage", "=", "internal"),
                ("location_dest_id.usage", "=", "customer"),
            ]

            # Última semana
            week_ago = today - timedelta(days=7)
            moves_week = StockMove.search(base_domain + [("date", ">=", week_ago)])
            line.sales_last_week = sum(moves_week.mapped("product_uom_qty"))

            # Último mes
            month_ago = today - timedelta(days=30)
            moves_month = StockMove.search(base_domain + [("date", ">=", month_ago)])
            line.sales_last_month = sum(moves_month.mapped("product_uom_qty"))

            # Últimos 3 meses
            three_months_ago = today - timedelta(days=90)
            moves_3m = StockMove.search(
                base_domain + [("date", ">=", three_months_ago)]
            )
            line.sales_last_3_months = sum(moves_3m.mapped("product_uom_qty"))

            # Últimos 6 meses
            six_months_ago = today - timedelta(days=180)
            moves_6m = StockMove.search(base_domain + [("date", ">=", six_months_ago)])
            line.sales_last_6_months = sum(moves_6m.mapped("product_uom_qty"))

            # Promedio diario (basado en 90 días)
            line.avg_daily_sales = (
                line.sales_last_3_months / 90 if line.sales_last_3_months else 0
            )

    def _compute_stock_by_warehouse(self):
        """Calcular stock disponible por cada almacén en formato HTML visual"""
        for line in self:
            if not line.product_id:
                line.stock_by_warehouse = (
                    '<span style="color: #888;">Sin producto</span>'
                )
                continue

            # Obtener todos los almacenes activos
            warehouses = self.env["stock.warehouse"].search(
                [("active_intelligence", "=", True)]
            )

            if not warehouses:
                line.stock_by_warehouse = (
                    '<span style="color: #888;">Sin almacenes</span>'
                )
                continue

            html_parts = []
            total_qty = 0

            for warehouse in warehouses:
                # Obtener cantidad disponible en este almacén
                quant = self.env["stock.quant"].search(
                    [
                        ("product_id", "=", line.product_id.id),
                        ("location_id", "child_of", warehouse.lot_stock_id.id),
                    ],
                    limit=1,
                )

                qty = sum(
                    self.env["stock.quant"]
                    .search(
                        [
                            ("product_id", "=", line.product_id.id),
                            ("location_id", "child_of", warehouse.lot_stock_id.id),
                        ]
                    )
                    .mapped("quantity")
                )

                total_qty += qty

                # Definir color según cantidad
                if qty <= 0:
                    color = "#dc3545"  # Rojo
                    bg_color = "#f8d7da"
                    icon = "⚠️"
                elif qty < 10:
                    color = "#fd7e14"  # Naranja
                    bg_color = "#ffe5d0"
                    icon = "⚡"
                else:
                    color = "#28a745"  # Verde
                    bg_color = "#d4edda"
                    icon = "✅"

                html_parts.append(f"""
                    <div style="display: inline-block; margin: 2px 8px 2px 0; padding: 4px 10px; 
                                border-radius: 6px; background: {bg_color}; border-left: 4px solid {color};">
                        <span style="font-weight: 600; color: #333;">{icon} {warehouse.name}:</span>
                        <span style="font-weight: 700; color: {color}; margin-left: 4px;">{qty:.0f}</span>
                    </div>
                """)

            # Agregar total
            total_color = "#28a745" if total_qty > 0 else "#dc3545"
            html_parts.append(f"""
                <div style="display: inline-block; margin: 2px 0; padding: 4px 12px; 
                            border-radius: 6px; background: #e7f3ff; border: 2px solid #0d6efd;">
                    <span style="font-weight: 600; color: #0d6efd;">📦 TOTAL:</span>
                    <span style="font-weight: 700; color: {total_color}; margin-left: 4px;">{total_qty:.0f}</span>
                </div>
            """)

            line.stock_by_warehouse = (
                '<div style="display: flex; flex-wrap: wrap; align-items: center; gap: 4px;">'
                + "".join(html_parts)
                + "</div>"
            )

    def _compute_stock_coverage(self):
        """Calcular días de cobertura con el stock actual + cantidad pedida"""
        for line in self:
            if line.avg_daily_sales > 0:
                total_stock = line.current_stock + line.product_qty
                line.stock_coverage_days = total_stock / line.avg_daily_sales
            else:
                line.stock_coverage_days = 999  # Sin ventas = cobertura infinita

    def _compute_last_purchase(self):
        """Encontrar información de la última compra del producto"""
        today = fields.Date.context_today(self)

        for line in self:
            if not line.product_id:
                line.last_purchase_date = False
                line.last_purchase_price = 0
                line.last_purchase_qty = 0
                line.last_supplier = ""
                line.days_since_purchase = 0
                continue

            # Buscar última línea de compra confirmada de este producto
            last_line = self.env["purchase.order.line"].search(
                [
                    ("product_id", "=", line.product_id.id),
                    ("order_id.state", "in", ["purchase", "done"]),
                    ("id", "!=", line.id),  # Excluir la línea actual
                ],
                order="date_order desc",
                limit=1,
            )

            if last_line:
                line.last_purchase_date = (
                    last_line.date_order.date() if last_line.date_order else False
                )
                line.last_purchase_price = last_line.price_unit
                line.last_purchase_qty = last_line.product_qty
                line.last_supplier = last_line.order_id.partner_id.name
                if line.last_purchase_date:
                    line.days_since_purchase = (today - line.last_purchase_date).days
                else:
                    line.days_since_purchase = 0
            else:
                line.last_purchase_date = False
                line.last_purchase_price = 0
                line.last_purchase_qty = 0
                line.last_supplier = "Sin compras previas"
                line.days_since_purchase = 999

    def _compute_price_comparison(self):
        """Calcular comparación y tendencia de precios"""
        for line in self:
            # Comparar con última compra
            if line.last_purchase_price and line.last_purchase_price > 0:
                variation = (
                    (line.price_unit - line.last_purchase_price)
                    / line.last_purchase_price
                ) * 100
                line.price_variation = round(variation, 2)

                if variation > 2:
                    line.price_trend = "up"
                elif variation < -2:
                    line.price_trend = "down"
                else:
                    line.price_trend = "stable"
            else:
                line.price_variation = 0
                line.price_trend = "stable"

            # Margen vs costo estándar
            if line.standard_price and line.standard_price > 0:
                line.margin_vs_standard = round(
                    ((line.price_unit - line.standard_price) / line.standard_price)
                    * 100,
                    2,
                )
            else:
                line.margin_vs_standard = 0

    def _compute_recommendation(self):
        """Generar recomendación de cantidad basada en análisis"""
        for line in self:
            if line.avg_daily_sales <= 0:
                line.qty_recommendation = line.product_qty
                line.recommendation_reason = "Sin datos de venta"
                continue

            # Calcular cantidad para 30 días de cobertura
            target_days = 30
            needed_qty = (line.avg_daily_sales * target_days) - line.current_stock

            # Incluir también la demanda del pipeline
            if hasattr(line, "total_sales_pipeline") and line.total_sales_pipeline:
                needed_qty += line.total_sales_pipeline

            if needed_qty <= 0:
                line.qty_recommendation = 0
                line.recommendation_reason = f"Stock suficiente para {int(line.current_stock / line.avg_daily_sales)} días"
            else:
                # Redondear a múltiplos de 10
                line.qty_recommendation = round(needed_qty / 10) * 10
                line.recommendation_reason = f"Para 30 días de cobertura"

    def _compute_sales_pipeline(self):
        """Calcular demanda del pipeline de ventas (cotizaciones + órdenes confirmadas)"""
        for line in self:
            if not line.product_id:
                line.pending_quotations_qty = 0
                line.pending_quotations_count = 0
                line.confirmed_undelivered_qty = 0
                line.confirmed_undelivered_count = 0
                line.total_sales_pipeline = 0
                continue

            # Cotizaciones pendientes (draft, sent)
            quotation_lines = self.env["sale.order.line"].search(
                [
                    ("product_id", "=", line.product_id.id),
                    ("order_id.state", "in", ["draft", "sent"]),
                ]
            )
            line.pending_quotations_qty = sum(quotation_lines.mapped("product_uom_qty"))
            line.pending_quotations_count = len(quotation_lines.mapped("order_id"))

            # Órdenes confirmadas pero no entregadas completamente
            confirmed_lines = (
                self.env["sale.order.line"]
                .search(
                    [
                        ("product_id", "=", line.product_id.id),
                        ("order_id.state", "in", ["sale", "done"]),
                    ]
                )
                .filtered(lambda l: l.qty_delivered < l.product_uom_qty)
            )
            pending_delivery = sum(
                sol.product_uom_qty - sol.qty_delivered for sol in confirmed_lines
            )
            line.confirmed_undelivered_qty = pending_delivery
            line.confirmed_undelivered_count = len(confirmed_lines.mapped("order_id"))

            # Total del pipeline
            line.total_sales_pipeline = (
                line.pending_quotations_qty + line.confirmed_undelivered_qty
            )

    def _compute_lost_sales_risk(self):
        """Calcular el riesgo de ventas perdidas y la fecha de agotamiento proyectada"""
        today = fields.Date.context_today(self)

        for line in self:
            if not line.product_id:
                line.lost_sales_risk_qty = 0
                line.lost_sales_risk_amount = 0
                line.projected_stockout_date = False
                continue

            # Calcular déficit: demanda del pipeline - stock disponible
            shortage = line.total_sales_pipeline - line.current_stock

            if shortage > 0:
                line.lost_sales_risk_qty = shortage
                # Usar el precio de venta para calcular el valor en riesgo
                sale_price = line.product_id.list_price or (line.price_unit * 1.3)
                line.lost_sales_risk_amount = shortage * sale_price
            else:
                line.lost_sales_risk_qty = 0
                line.lost_sales_risk_amount = 0

            # Calcular fecha de agotamiento
            if line.avg_daily_sales > 0:
                days_until_stockout = line.current_stock / line.avg_daily_sales
                line.projected_stockout_date = today + timedelta(
                    days=int(days_until_stockout)
                )
            else:
                line.projected_stockout_date = False
