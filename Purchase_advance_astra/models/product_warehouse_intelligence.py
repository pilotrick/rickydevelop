# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ProductWarehouseIntelligence(models.Model):
    _name = 'pi.product.warehouse.intelligence'
    _description = 'Inteligencia de Stock por Almacén'
    _order = 'warehouse_id, product_id'

    product_id = fields.Many2one('product.template', string='Producto', required=True, ondelete='cascade')
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True, ondelete='cascade')
    
    # Métricas de Consumo
    daily_usage = fields.Float(string='Consumo Diario', digits=(16, 2))
    weekly_usage = fields.Float(string='Consumo Semanal', digits=(16, 2))
    monthly_usage = fields.Float(string='Consumo Mensual', digits=(16, 2))
    lead_time_days = fields.Integer(string='Tiempo de Entrega (Días)')
    
    # Inteligencia de Stock
    safety_stock = fields.Float(string='Stock de Seguridad', digits=(16, 2))
    reorder_point = fields.Float(string='Punto de Reorden', digits=(16, 2))
    max_stock = fields.Float(string='Stock Máximo', digits=(16, 2))
    eoq = fields.Float(string='EOQ', digits=(16, 2))
    
    # Estado Actual
    qty_available = fields.Float(string='Stock Disponible', digits=(16, 2))
    days_of_stock = fields.Float(string='Días de Stock', digits=(16, 1))
    
    # Sugerencias
    needs_reorder = fields.Boolean(string='¿Necesita Pedido?')
    suggested_order_qty = fields.Float(string='Cantidad Sugerida', digits=(16, 2))

    # Riesgo y Clasificación
    stockout_risk = fields.Selection([
        ('none', 'Sin Riesgo'),
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', 'CRÍTICO')
    ], string='Riesgo')
    
    abc_classification = fields.Selection([
        ('A', 'A - Valor Alto'),
        ('B', 'B - Valor Medio'),
        ('C', 'C - Valor Bajo')
    ], string='ABC')

    fsn_classification = fields.Selection([
        ('F', 'Rápido (Fast)'),
        ('S', 'Lento (Slow)'),
        ('N', 'Sin Movimiento (Non-moving)'),
        ('D', 'Muerto (Dead)')
    ], string='FSN')

    ved_classification = fields.Selection([
        ('V', 'Vital'),
        ('E', 'Esencial'),
        ('D', 'Deseable')
    ], string='VED', default='D')

    suggestion_state = fields.Selection([
        ('normal', 'Normal'),
        ('reorder', 'Reordenar'),
        ('overstock', 'Exceso')
    ], string='Estado', compute='_compute_suggestion_state', store=True)

    @api.depends('stockout_risk', 'days_of_stock')
    def _compute_suggestion_state(self):
        for record in self:
            if record.stockout_risk in ['high', 'critical']:
                record.suggestion_state = 'reorder'
            elif record.days_of_stock > 180:
                record.suggestion_state = 'overstock'
            else:
                record.suggestion_state = 'normal'
