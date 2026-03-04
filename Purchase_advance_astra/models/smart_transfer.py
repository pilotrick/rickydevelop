# -*- coding: utf-8 -*-
"""
Smart Inter-Warehouse Transfer System
Automatically suggests stock transfers between warehouses to balance inventory
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class SmartTransferSuggestion(models.Model):
    _name = "pi.smart.transfer"
    _description = "Sugerencia de Transferencia Inteligente entre Almacenes"
    _order = "priority desc, create_date desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    name = fields.Char("Referencia", compute="_compute_name", store=True)
    product_id = fields.Many2one(
        "product.product", "Producto", required=True, index=True
    )

    # Source Warehouse (excess stock)
    source_warehouse_id = fields.Many2one(
        "stock.warehouse", "Almacén Origen", required=True
    )
    source_stock = fields.Float("Stock en Origen", digits="Product Unit of Measure")
    source_available = fields.Float(
        "Disponible en Origen", digits="Product Unit of Measure"
    )

    # Destination Warehouse (shortage)
    dest_warehouse_id = fields.Many2one(
        "stock.warehouse", "Almacén Destino", required=True
    )
    dest_stock = fields.Float("Stock en Destino", digits="Product Unit of Measure")
    dest_available = fields.Float(
        "Disponible en Destino", digits="Product Unit of Measure"
    )
    dest_shortage = fields.Float(
        "Faltante en Destino", digits="Product Unit of Measure"
    )

    # Transfer Details
    suggested_qty = fields.Float(
        "Cantidad Sugerida",
        digits="Product Unit of Measure",
        compute="_compute_suggested_qty",
        store=True,
    )
    transfer_status = fields.Selection(
        [
            ("suggested", "Sugerida"),
            ("approved", "Aprobada"),
            ("in_transit", "En Tránsito"),
            ("completed", "Completada"),
            ("cancelled", "Cancelada"),
        ],
        default="suggested",
        tracking=True,
    )

    priority = fields.Selection(
        [
            ("low", "🟢 Baja"),
            ("medium", "🟡 Media"),
            ("high", "🟠 Alta"),
            ("critical", "🔴 Crítica"),
        ],
        compute="_compute_priority",
        store=True,
    )

    # Financial Impact
    product_value = fields.Float("Valor Unitario", compute="_compute_value", store=True)
    transfer_value = fields.Float(
        "Valor Total Transferencia", compute="_compute_value", store=True
    )

    # Days until stockout at destination
    days_until_stockout = fields.Float("Días hasta Rotura en Destino")

    # Execution
    picking_id = fields.Many2one(
        "stock.picking", "Transferencia Relacionada", readonly=True
    )
    transfer_date = fields.Datetime("Fecha de Transferencia")

    # Analytics
    potential_lost_sales = fields.Float(
        "Ventas Perdidas Potenciales", help="Estimated lost sales if not transferred"
    )
    roi_score = fields.Float("ROI Score", help="Higher = more urgent to transfer")

    @api.depends("product_id", "source_warehouse_id", "dest_warehouse_id")
    def _compute_name(self):
        for rec in self:
            rec.name = f"TRF/{rec.product_id.default_code or rec.product_id.id}/{rec.source_warehouse_id.code or 'WH'}-{rec.dest_warehouse_id.code or 'WH'}"

    @api.depends("source_stock", "dest_stock", "dest_shortage")
    def _compute_suggested_qty(self):
        """Calculate optimal transfer quantity"""
        for rec in self:
            # Transfer the minimum of: what source can spare, what destination needs
            # Keep safety buffer at source (30 days of stock)
            source_safety = rec.source_stock * 0.3  # Keep 30% as buffer

            available_to_transfer = max(0, rec.source_available - source_safety)
            needed_at_dest = rec.dest_shortage

            rec.suggested_qty = min(available_to_transfer, needed_at_dest)

    @api.depends("suggested_qty", "product_id")
    def _compute_value(self):
        for rec in self:
            rec.product_value = rec.product_id.standard_price or 0
            rec.transfer_value = rec.suggested_qty * rec.product_value

    @api.depends("days_until_stockout", "dest_shortage", "transfer_value")
    def _compute_priority(self):
        """Calculate priority based on urgency and value"""
        for rec in self:
            if rec.days_until_stockout <= 3:
                rec.priority = "critical"
            elif rec.days_until_stockout <= 7:
                rec.priority = "high"
            elif rec.days_until_stockout <= 14:
                rec.priority = "medium"
            else:
                rec.priority = "low"

    def action_create_transfer(self):
        """Create stock transfer between warehouses"""
        self.ensure_one()

        if self.suggested_qty <= 0:
            raise UserError(_("No hay cantidad válida para transferir"))

        if self.transfer_status != "suggested":
            raise UserError(_("Esta transferencia ya fue procesada"))

        # Find internal transfer picking type
        picking_type = self.env["stock.picking.type"].search(
            [
                ("code", "=", "internal"),
                ("warehouse_id", "=", self.source_warehouse_id.id),
                (
                    "default_location_dest_id.warehouse_id",
                    "=",
                    self.dest_warehouse_id.id,
                ),
            ],
            limit=1,
        )

        if not picking_type:
            # Fallback: create manually
            picking_type = self.env["stock.picking.type"].search(
                [
                    ("code", "=", "internal"),
                    ("warehouse_id", "=", self.source_warehouse_id.id),
                ],
                limit=1,
            )

        if not picking_type:
            raise UserError(_("No se encontró tipo de transferencia interna"))

        # Create picking
        picking = self.env["stock.picking"].create(
            {
                "picking_type_id": picking_type.id,
                "location_id": self.source_warehouse_id.lot_stock_id.id,
                "location_dest_id": self.dest_warehouse_id.lot_stock_id.id,
                "move_ids": [
                    (
                        0,
                        0,
                        {
                            "name": self.product_id.name,
                            "product_id": self.product_id.id,
                            "product_uom_qty": self.suggested_qty,
                            "product_uom": self.product_id.uom_id.id,
                            "location_id": self.source_warehouse_id.lot_stock_id.id,
                            "location_dest_id": self.dest_warehouse_id.lot_stock_id.id,
                        },
                    )
                ],
                "origin": self.name,
                "note": f"Transferencia sugerida automáticamente. Prioridad: {self.priority}",
            }
        )

        self.write(
            {
                "picking_id": picking.id,
                "transfer_status": "approved",
                "transfer_date": fields.Datetime.now(),
            }
        )

        # Confirm the picking
        picking.action_confirm()

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": picking.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_complete(self):
        """Mark transfer as completed"""
        self.write({"transfer_status": "completed"})

    def action_cancel(self):
        """Cancel transfer suggestion"""
        self.write({"transfer_status": "cancelled"})

    def action_view_picking(self):
        """View the related stock picking"""
        self.ensure_one()
        if not self.picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "res_id": self.picking_id.id,
            "view_mode": "form",
            "target": "current",
        }

    @api.model
    def cron_generate_transfer_suggestions(self):
        """
        Cron: Generate smart transfer suggestions
        Run daily to find imbalances between warehouses
        """
        _logger.info("=== Generating Smart Transfer Suggestions ===")

        warehouses = self.env["stock.warehouse"].search([])
        products = self.env["product.product"].search(
            [
                ("type", "=", "product"),
                ("purchase_ok", "=", True),
            ]
        )

        suggestions_created = 0

        for product in products:
            # Get stock per warehouse
            stock_by_wh = {}
            for wh in warehouses:
                quants = self.env["stock.quant"].search(
                    [
                        ("product_id", "=", product.id),
                        ("location_id", "child_of", wh.lot_stock_id.id),
                    ]
                )
                quantity = sum(q.quantity for q in quants)
                reserved = sum(q.reserved_quantity for q in quants)
                available = quantity - reserved

                # Get daily usage for this warehouse
                date_from = fields.Date.today() - timedelta(days=30)
                moves = self.env["stock.move"].search(
                    [
                        ("product_id", "=", product.id),
                        ("location_id.warehouse_id", "=", wh.id),
                        ("state", "=", "done"),
                        ("date", ">=", date_from),
                    ]
                )
                daily_usage = (
                    sum(
                        m.product_uom_qty
                        for m in moves
                        if m.location_dest_id.usage != "internal"
                    )
                    / 30
                )

                days_of_stock = available / daily_usage if daily_usage > 0 else 999

                stock_by_wh[wh.id] = {
                    "quantity": quantity,
                    "available": available,
                    "daily_usage": daily_usage,
                    "days_of_stock": days_of_stock,
                }

            # Find imbalances: excess in one, shortage in another
            excess_warehouses = [
                (wh_id, data)
                for wh_id, data in stock_by_wh.items()
                if data["days_of_stock"] > 60 and data["available"] > 10
            ]

            shortage_warehouses = [
                (wh_id, data)
                for wh_id, data in stock_by_wh.items()
                if data["days_of_stock"] < 14 and data["available"] < 10
            ]

            # Create suggestions for each combination
            for src_wh_id, src_data in excess_warehouses:
                for dest_wh_id, dest_data in shortage_warehouses:
                    if src_wh_id == dest_wh_id:
                        continue

                    # Check if suggestion already exists
                    existing = self.search(
                        [
                            ("product_id", "=", product.id),
                            ("source_warehouse_id", "=", src_wh_id),
                            ("dest_warehouse_id", "=", dest_wh_id),
                            ("transfer_status", "=", "suggested"),
                        ],
                        limit=1,
                    )

                    if existing:
                        continue

                    shortage = (dest_data["daily_usage"] * 30) - dest_data["available"]

                    self.create(
                        {
                            "product_id": product.id,
                            "source_warehouse_id": src_wh_id,
                            "source_stock": src_data["quantity"],
                            "source_available": src_data["available"],
                            "dest_warehouse_id": dest_wh_id,
                            "dest_stock": dest_data["quantity"],
                            "dest_available": dest_data["available"],
                            "dest_shortage": max(0, shortage),
                            "days_until_stockout": dest_data["days_of_stock"],
                        }
                    )
                    suggestions_created += 1

        _logger.info(f"=== Created {suggestions_created} transfer suggestions ===")
        return True

    @api.model
    def get_transfer_dashboard_data(self):
        """Get data for transfer dashboard"""
        suggestions = self.search(
            [("transfer_status", "=", "suggested")],
            order="priority desc, days_until_stockout asc",
            limit=20,
        )

        stats = {
            "total_suggested": self.search_count(
                [("transfer_status", "=", "suggested")]
            ),
            "critical": self.search_count(
                [("transfer_status", "=", "suggested"), ("priority", "=", "critical")]
            ),
            "high": self.search_count(
                [("transfer_status", "=", "suggested"), ("priority", "=", "high")]
            ),
            "in_transit": self.search_count([("transfer_status", "=", "in_transit")]),
            "total_value": sum(
                self.search([("transfer_status", "=", "suggested")]).mapped(
                    "transfer_value"
                )
            ),
        }

        return {
            "stats": stats,
            "suggestions": [
                {
                    "id": s.id,
                    "product_name": s.product_id.display_name,
                    "source": s.source_warehouse_id.name,
                    "dest": s.dest_warehouse_id.name,
                    "qty": s.suggested_qty,
                    "priority": s.priority,
                    "days": s.days_until_stockout,
                    "value": s.transfer_value,
                }
                for s in suggestions
            ],
        }
