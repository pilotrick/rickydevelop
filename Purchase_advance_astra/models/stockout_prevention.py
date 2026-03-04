# -*- coding: utf-8 -*-
"""
Stockout Prevention System - NEVER RUN OUT OF STOCK AGAIN!
Auto-calculates safety stock per warehouse and creates proactive alerts
"""
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging
import math

_logger = logging.getLogger(__name__)


class StockoutPrevention(models.Model):
    _name = 'pi.stockout.prevention'
    _description = 'Sistema de Prevención de Roturas de Stock'
    _order = 'priority desc, days_until_stockout asc'
    
    name = fields.Char('Nombre', compute='_compute_name', store=True)
    product_id = fields.Many2one('product.product', 'Producto', required=True, index=True)
    warehouse_id = fields.Many2one('stock.warehouse', 'Almacén', required=True, index=True)
    
    # Stock Levels
    current_stock = fields.Float('Stock Actual', digits='Product Unit of Measure')
    reserved_stock = fields.Float('Stock Reservado', digits='Product Unit of Measure')
    available_stock = fields.Float('Stock Disponible', compute='_compute_available_stock', store=True)
    
    # Calculated Metrics
    daily_usage = fields.Float('Consumo Diario', digits='Product Unit of Measure')
    days_until_stockout = fields.Float('Días hasta Rotura', compute='_compute_days_until_stockout', store=True)
    
    # Safety Stock (Auto-calculated)
    safety_stock = fields.Float('Stock de Seguridad', digits='Product Unit of Measure', 
                                compute='_compute_safety_stock', store=True)
    safety_stock_days = fields.Integer('Días de Stock de Seguridad', default=7)
    
    # Reorder Point (Auto-calculated)
    reorder_point = fields.Float('Punto de Reorden', digits='Product Unit of Measure',
                                  compute='_compute_reorder_point', store=True)
    
    # Lead Time
    lead_time_days = fields.Integer('Tiempo de Entrega (días)', default=7)
    
    # Risk Assessment
    stockout_risk = fields.Selection([
        ('none', 'Sin Riesgo'),
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', '🔴 CRÍTICO - PEDIR YA!'),
        ('stockout', '⛔ SIN STOCK'),
    ], string='Riesgo de Rotura', compute='_compute_stockout_risk', store=True)
    
    priority = fields.Integer('Prioridad', compute='_compute_priority', store=True)
    
    # Suggested Order
    suggested_order_qty = fields.Float('Cantidad Sugerida', digits='Product Unit of Measure',
                                        compute='_compute_suggested_order', store=True)
    estimated_cost = fields.Float('Costo Estimado', compute='_compute_estimated_cost', store=True)
    
    # Supplier Info
    supplier_id = fields.Many2one('res.partner', 'Proveedor Preferido', compute='_compute_supplier', store=True)
    supplier_lead_time = fields.Integer('Tiempo Proveedor (días)', compute='_compute_supplier', store=True)
    
    # Status
    state = fields.Selection([
        ('monitoring', 'Monitoreando'),
        ('alert_sent', 'Alerta Enviada'),
        ('order_created', 'Orden Creada'),
        ('resolved', 'Resuelto'),
    ], default='monitoring')
    
    alert_sent = fields.Boolean('Alerta Enviada', default=False)
    alert_date = fields.Datetime('Fecha de Alerta')
    
    # History
    stockout_history_count = fields.Integer('Roturas Históricas', default=0)
    last_stockout_date = fields.Date('Última Rotura')
    
    
    @api.depends('product_id', 'warehouse_id')
    def _compute_name(self):
        for rec in self:
            rec.name = f"{rec.product_id.display_name or ''} - {rec.warehouse_id.name or ''}"
    
    @api.depends('current_stock', 'reserved_stock')
    def _compute_available_stock(self):
        for rec in self:
            rec.available_stock = max(0, rec.current_stock - rec.reserved_stock)
    
    @api.depends('available_stock', 'daily_usage')
    def _compute_days_until_stockout(self):
        for rec in self:
            if rec.daily_usage > 0:
                rec.days_until_stockout = rec.available_stock / rec.daily_usage
            else:
                rec.days_until_stockout = 999  # Sin consumo, mucho tiempo
    
    @api.depends('daily_usage', 'lead_time_days', 'stockout_history_count')
    def _compute_safety_stock(self):
        """
        Auto-calculate safety stock based on:
        - Daily usage variability
        - Lead time
        - Historical stockout frequency
        
        Formula: Safety Stock = Z * σ * √(Lead Time)
        Where:
        - Z = Service factor (1.65 for 95% service level)
        - σ = Standard deviation of demand
        """
        for rec in self:
            if rec.daily_usage > 0:
                # Service factor for 95% service level
                z_factor = 1.65
                
                # Estimate variability (higher if historical stockouts)
                variability_factor = 1.0 + (rec.stockout_history_count * 0.1)
                
                # Calculate safety stock
                safety_stock = z_factor * rec.daily_usage * math.sqrt(rec.lead_time_days) * variability_factor
                
                # Minimum safety stock = safety_stock_days of consumption
                min_safety = rec.daily_usage * rec.safety_stock_days
                
                rec.safety_stock = max(safety_stock, min_safety)
            else:
                rec.safety_stock = 0
    
    @api.depends('daily_usage', 'lead_time_days', 'safety_stock')
    def _compute_reorder_point(self):
        """
        Auto-calculate reorder point:
        ROP = (Daily Usage × Lead Time) + Safety Stock
        """
        for rec in self:
            rec.reorder_point = (rec.daily_usage * rec.lead_time_days) + rec.safety_stock
    
    @api.depends('available_stock', 'reorder_point', 'safety_stock', 'days_until_stockout')
    def _compute_stockout_risk(self):
        for rec in self:
            if rec.available_stock <= 0:
                rec.stockout_risk = 'stockout'
            elif rec.available_stock < rec.safety_stock:
                rec.stockout_risk = 'critical'
            elif rec.days_until_stockout <= rec.lead_time_days:
                rec.stockout_risk = 'high'
            elif rec.available_stock < rec.reorder_point:
                rec.stockout_risk = 'medium'
            elif rec.days_until_stockout <= rec.lead_time_days * 2:
                rec.stockout_risk = 'low'
            else:
                rec.stockout_risk = 'none'
    
    @api.depends('stockout_risk', 'days_until_stockout')
    def _compute_priority(self):
        """Higher priority = more urgent"""
        priority_map = {
            'stockout': 100,
            'critical': 90,
            'high': 70,
            'medium': 50,
            'low': 30,
            'none': 10,
        }
        for rec in self:
            base = priority_map.get(rec.stockout_risk, 0)
            # Boost priority if stockout is imminent
            if rec.days_until_stockout < 3:
                base += 20
            elif rec.days_until_stockout < 7:
                base += 10
            rec.priority = base
    
    @api.depends('reorder_point', 'available_stock', 'daily_usage', 'lead_time_days')
    def _compute_suggested_order(self):
        """
        Calculate optimal order quantity using EOQ formula:
        EOQ = √(2 × D × S / H)
        Where:
        - D = Annual demand
        - S = Ordering cost
        - H = Holding cost
        """
        for rec in self:
            if rec.daily_usage > 0:
                # Annual demand
                annual_demand = rec.daily_usage * 365
                
                # Order to reach max stock level (cover lead time + safety period)
                target_stock = rec.reorder_point + (rec.daily_usage * 30)  # 30 days coverage
                needed_qty = max(0, target_stock - rec.available_stock)
                
                # Minimum order = EOQ or enough to cover lead time + buffer
                min_order = rec.daily_usage * (rec.lead_time_days + 14)
                
                rec.suggested_order_qty = max(needed_qty, min_order)
            else:
                rec.suggested_order_qty = 0
    
    @api.depends('suggested_order_qty', 'product_id')
    def _compute_estimated_cost(self):
        for rec in self:
            rec.estimated_cost = rec.suggested_order_qty * (rec.product_id.standard_price or 0)
    
    @api.depends('product_id')
    def _compute_supplier(self):
        for rec in self:
            supplierinfo = rec.product_id.seller_ids[:1]
            if supplierinfo:
                rec.supplier_id = supplierinfo.partner_id.id
                rec.supplier_lead_time = supplierinfo.delay or 7
            else:
                rec.supplier_id = False
                rec.supplier_lead_time = 7
    
    @api.model
    def cron_update_all_prevention_records(self):
        """
        Scheduled action to update all stockout prevention records
        Runs every hour to keep data fresh
        """
        _logger.info("=== STOCKOUT PREVENTION: Updating all records ===")
        
        # Get all storable products with stock
        products = self.env['product.product'].search([
            ('type', '=', 'product'),
            ('purchase_ok', '=', True),
        ])
        
        warehouses = self.env['stock.warehouse'].search([])
        
        created = 0
        updated = 0
        
        for warehouse in warehouses:
            for product in products:
                # Get current stock in this warehouse
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id.warehouse_id', '=', warehouse.id),
                ])
                
                current_stock = sum(q.quantity for q in quants)
                reserved_stock = sum(q.reserved_quantity for q in quants)
                
                # Get daily usage (last 30 days)
                date_from = fields.Date.today() - timedelta(days=30)
                moves = self.env['stock.move'].search([
                    ('product_id', '=', product.id),
                    ('location_id.warehouse_id', '=', warehouse.id),
                    ('state', '=', 'done'),
                    ('date', '>=', date_from),
                ])
                total_out = sum(m.product_uom_qty for m in moves if m.location_dest_id.usage != 'internal')
                daily_usage = total_out / 30 if total_out > 0 else 0
                
                # Get lead time from supplier
                lead_time = 7
                if product.seller_ids:
                    lead_time = product.seller_ids[0].delay or 7
                
                # Check stockout history
                stockout_moves = self.env['stock.move'].search([
                    ('product_id', '=', product.id),
                    ('location_id.warehouse_id', '=', warehouse.id),
                    ('state', '=', 'done'),
                    ('date', '>=', fields.Date.today() - timedelta(days=365)),
                ], limit=10)
                
                # Create or update record
                existing = self.search([
                    ('product_id', '=', product.id),
                    ('warehouse_id', '=', warehouse.id),
                ])
                
                vals = {
                    'current_stock': current_stock,
                    'reserved_stock': reserved_stock,
                    'daily_usage': daily_usage,
                    'lead_time_days': lead_time,
                    'stockout_history_count': len(stockout_moves),
                }
                
                if existing:
                    existing.write(vals)
                    updated += 1
                else:
                    vals.update({
                        'product_id': product.id,
                        'warehouse_id': warehouse.id,
                    })
                    self.create(vals)
                    created += 1
        
        _logger.info(f"=== STOCKOUT PREVENTION: Created {created}, Updated {updated} ===")
        
        # Send alerts for critical items
        self._send_stockout_alerts()
        
        return True
    
    def _send_stockout_alerts(self):
        """Send alerts for critical stockout risks"""
        critical_records = self.search([
            ('stockout_risk', 'in', ['critical', 'stockout']),
            ('alert_sent', '=', False),
        ])
        
        for rec in critical_records:
            # Create alert log
            self.env['pi.alert.log'].create({
                'name': f'🔴 ALERTA DE ROTURA: {rec.product_id.display_name}',
                'message': f"""
El producto {rec.product_id.display_name} en {rec.warehouse_id.name} está en riesgo de rotura!

Stock Actual: {rec.current_stock}
Stock Disponible: {rec.available_stock}
Días hasta Rotura: {rec.days_until_stockout:.1f}
Cantidad Sugerida a Pedir: {rec.suggested_order_qty}
Proveedor: {rec.supplier_id.name or 'Sin proveedor'}

ACCIÓN INMEDIATA: Crear orden de compra
                """,
                'severity': 'critical',
                'res_model': 'product.product',
                'res_id': rec.product_id.id,
                'state': 'new',
            })
            
            rec.write({
                'alert_sent': True,
                'alert_date': fields.Datetime.now(),
                'state': 'alert_sent',
            })
            
            _logger.warning(f"STOCKOUT ALERT: {rec.product_id.display_name} in {rec.warehouse_id.name}")
    
    def action_view_product(self):
        """View the product"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }


    def action_create_purchase_order(self):
        """Create a purchase order for this product"""
        self.ensure_one()
        
        if not self.supplier_id:
            raise UserError(_("No hay proveedor configurado para este producto"))
        
        # Create PO
        po = self.env['purchase.order'].create({
            'partner_id': self.supplier_id.id,
            'picking_type_id': self.warehouse_id.in_type_id.id,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.suggested_order_qty,
                'price_unit': self.product_id.standard_price,
            })],
        })
        
        self.write({
            'state': 'order_created',
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.model
    def get_critical_products(self, warehouse_id=None):
        """Get all critical products for dashboard"""
        domain = [('stockout_risk', 'in', ['critical', 'high', 'stockout'])]
        if warehouse_id:
            domain.append(('warehouse_id', '=', warehouse_id))
        
        records = self.search(domain, order='priority desc, days_until_stockout asc', limit=20)
        
        return [{
            'id': r.id,
            'product_name': r.product_id.display_name,
            'warehouse_name': r.warehouse_id.name,
            'current_stock': r.current_stock,
            'available_stock': r.available_stock,
            'days_until_stockout': round(r.days_until_stockout, 1),
            'stockout_risk': r.stockout_risk,
            'priority': r.priority,
            'suggested_order_qty': round(r.suggested_order_qty, 2),
            'supplier_name': r.supplier_id.name or 'Sin proveedor',
            'estimated_cost': r.estimated_cost,
        } for r in records]
