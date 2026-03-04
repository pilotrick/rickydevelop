# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)

class PurchaseIntelligenceForecast(models.Model):
    _name = 'purchase.intelligence.forecast'
    _description = 'Previsión de Demanda'

    product_id = fields.Many2one('product.product', string='Producto', required=True)
    date = fields.Date(string='Fecha de Previsión', required=True)
    forecast_qty = fields.Float(string='Cantidad Prevista')
    confidence = fields.Float(string='Nivel de Confianza (%)')
    method = fields.Selection([
        ('time_series', 'Series Temporales'),
        ('machine_learning', 'Aprendizaje Automático'),
        ('manual', 'Ajuste Manual')
    ], string='Método', default='time_series')
    notes = fields.Text(string='Notas')

    @api.model
    def action_update_forecasts(self):
        """
        Método Cron: Actualizar previsiones basadas en datos históricos de compras
        """
        _logger.info("Iniciando actualización de previsiones de demanda...")
        
        today = fields.Date.context_today(self)
        three_months_ago = today - timedelta(days=90)
        six_months_ago = today - timedelta(days=180)
        
        # Obtener productos con movimientos de compra recientes
        products = self.env['product.product'].search([
            ('purchase_ok', '=', True),
            ('is_storable', '=', True)
        ])
        
        forecasts_created = 0
        for product in products:
            # Calcular demanda promedio basada en órdenes de compra
            po_lines = self.env['purchase.order.line'].search([
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ['purchase', 'done']),
                ('order_id.date_order', '>=', six_months_ago)
            ])
            
            if not po_lines:
                continue
            
            # Calcular cantidad total y promedio mensual
            total_qty = sum(po_lines.mapped('product_qty'))
            months = 6  # Período de análisis
            avg_monthly = total_qty / months if months > 0 else 0
            
            # Analizar tendencia (comparar últimos 3 meses vs primeros 3 meses)
            recent_lines = po_lines.filtered(lambda l: l.order_id.date_order.date() >= three_months_ago)
            older_lines = po_lines.filtered(lambda l: l.order_id.date_order.date() < three_months_ago)
            
            recent_qty = sum(recent_lines.mapped('product_qty'))
            older_qty = sum(older_lines.mapped('product_qty'))
            
            # Factor de tendencia
            if older_qty > 0:
                trend_factor = (recent_qty - older_qty) / older_qty
            else:
                trend_factor = 0
            
            # Previsión para próximo mes con ajuste de tendencia
            forecast_qty = avg_monthly * (1 + trend_factor * 0.5)
            
            # Calcular confianza basada en variabilidad
            confidence = 80 if len(po_lines) > 10 else 60 if len(po_lines) > 5 else 40
            
            # Crear o actualizar previsión
            forecast_date = today + timedelta(days=30)
            existing = self.search([
                ('product_id', '=', product.id),
                ('date', '>=', today),
                ('method', '=', 'time_series')
            ], limit=1)
            
            forecast_vals = {
                'product_id': product.id,
                'date': forecast_date,
                'forecast_qty': max(0, forecast_qty),
                'confidence': confidence,
                'method': 'time_series',
                'notes': f'Tendencia: {"Creciente" if trend_factor > 0.05 else "Decreciente" if trend_factor < -0.05 else "Estable"}'
            }
            
            if existing:
                existing.write(forecast_vals)
            else:
                self.create(forecast_vals)
                forecasts_created += 1
        
        _logger.info(f"Previsiones actualizadas. Nuevas creadas: {forecasts_created}")
        return True

class PurchaseIntelligenceAnalysis(models.Model):
    _name = 'purchase.intelligence.analysis'
    _description = 'Análisis de Inteligencia de Compras'
    _auto = True

    # Campos para análisis
    date = fields.Date(string='Fecha')
    category_id = fields.Many2one('product.category', string='Categoría')
    spend_amount = fields.Float(string='Monto de Gasto')
    savings_amount = fields.Float(string='Ahorros')

