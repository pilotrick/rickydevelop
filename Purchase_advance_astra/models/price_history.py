# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta

class PIPriceHistory(models.Model):
    _name = 'pi.price.history'
    _description = 'Historial de Precios de Compra'
    _order = 'date desc'

    product_id = fields.Many2one('product.product', string='Producto', required=True, index=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', index=True)
    date = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    price = fields.Float(string='Precio Unitario', required=True)
    currency_id = fields.Many2one('res.currency', string='Moneda', 
                                   default=lambda self: self.env.company.currency_id)
    quantity = fields.Float(string='Cantidad')
    purchase_order_id = fields.Many2one('purchase.order', string='Orden de Compra')
    
    # Análisis
    price_change = fields.Float(string='Cambio de Precio (%)', compute='_compute_price_change', store=True)
    trend = fields.Selection([
        ('up', 'Subiendo'),
        ('down', 'Bajando'),
        ('stable', 'Estable')
    ], string='Tendencia', compute='_compute_price_change', store=True)

    @api.depends('price', 'product_id', 'partner_id')
    def _compute_price_change(self):
        for record in self:
            # Buscar precio anterior del mismo producto/proveedor
            previous = self.search([
                ('product_id', '=', record.product_id.id),
                ('partner_id', '=', record.partner_id.id),
                ('date', '<', record.date),
                ('id', '!=', record.id)
            ], limit=1, order='date desc')
            
            if previous and previous.price:
                change = ((record.price - previous.price) / previous.price) * 100
                record.price_change = change
                if change > 2:
                    record.trend = 'up'
                elif change < -2:
                    record.trend = 'down'
                else:
                    record.trend = 'stable'
            else:
                record.price_change = 0.0
                record.trend = 'stable'

    @api.model
    def record_price_from_po(self, purchase_order):
        """Registrar precios desde una orden de compra confirmada"""
        for line in purchase_order.order_line:
            self.create({
                'product_id': line.product_id.id,
                'partner_id': purchase_order.partner_id.id,
                'date': purchase_order.date_order.date() if purchase_order.date_order else fields.Date.today(),
                'price': line.price_unit,
                'quantity': line.product_qty,
                'purchase_order_id': purchase_order.id,
            })

    @api.model
    def get_price_forecast(self, product_id, months=3):
        """Previsión simple de precios basada en tendencia histórica"""
        history = self.search([
            ('product_id', '=', product_id),
            ('date', '>=', fields.Date.today() - timedelta(days=365))
        ], order='date asc')
        
        if len(history) < 3:
            return {'forecast': 0, 'confidence': 0, 'trend': 'unknown'}
        
        prices = history.mapped('price')
        avg_price = sum(prices) / len(prices)
        
        # Tendencia simple: comparar primera mitad vs segunda mitad
        mid = len(prices) // 2
        first_half_avg = sum(prices[:mid]) / mid if mid > 0 else avg_price
        second_half_avg = sum(prices[mid:]) / (len(prices) - mid) if (len(prices) - mid) > 0 else avg_price
        
        trend_factor = (second_half_avg - first_half_avg) / first_half_avg if first_half_avg else 0
        forecast_price = avg_price * (1 + trend_factor * months / 12)
        
        return {
            'forecast': forecast_price,
            'confidence': 70 if len(history) > 10 else 50,
            'trend': 'up' if trend_factor > 0.02 else ('down' if trend_factor < -0.02 else 'stable')
        }
