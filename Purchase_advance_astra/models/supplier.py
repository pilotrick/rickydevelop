# -*- coding: utf-8 -*-
from odoo import models, fields, api

class ResPartner(models.Model):
    _inherit = 'res.partner'

    is_strategic = fields.Boolean(string='Es Proveedor Estratégico')
    supplier_score = fields.Float(string='Puntuación del Proveedor', compute='_compute_supplier_score', store=True)
    supplier_rank = fields.Integer(string='Ranking de Proveedor')
    
    # Definición de propiedades para criterios dinámicos de evaluación (Odoo 19)
    property_definition = fields.PropertiesDefinition(string='Definición de Criterios')
    
    risk_level = fields.Selection([
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto')
    ], string='Nivel de Riesgo', default='low')

    scorecard_ids = fields.One2many('pi.supplier.scorecard', 'partner_id', string='Cuadros de Mando')
    scorecard_count = fields.Integer(string='Contador Evaluaciones', compute='_compute_scorecard_count')

    @api.depends('scorecard_ids')
    def _compute_scorecard_count(self):
        for partner in self:
            partner.scorecard_count = len(partner.scorecard_ids)

    def action_view_scorecards(self):
        self.ensure_one()
        return {
            'name': 'Cuadros de Mando',
            'type': 'ir.actions.act_window',
            'res_model': 'pi.supplier.scorecard',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    @api.depends('scorecard_ids')
    def _compute_supplier_score(self):
        for partner in self:
            if partner.scorecard_ids:
                # Tomar el último puntaje
                partner.supplier_score = partner.scorecard_ids[0].overall_score
            else:
                partner.supplier_score = 0.0

class PISupplierScorecard(models.Model):
    _name = 'pi.supplier.scorecard'
    _description = 'Cuadro de Mando de Proveedor'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    date = fields.Date(string='Fecha de Evaluación', default=fields.Date.context_today)

    score_quality = fields.Float(string='Puntuación Calidad (0-10)')
    score_delivery = fields.Float(string='Puntuación Entrega (0-10)')
    score_price = fields.Float(string='Puntuación Precio (0-10)')
    score_service = fields.Float(string='Puntuación Servicio (0-10)')
    score_innovation = fields.Float(string='Puntuación Innovación (0-10)')

    # Campo Propiedades (Odoo 19) - Para criterios dinámicos de evaluación
    properties = fields.Properties(string='Criterios Dinámicos', definition='partner_id.property_definition')

    overall_score = fields.Float(string='Puntuación General', compute='_compute_overall_score', store=True)

    @api.depends('score_quality', 'score_delivery', 'score_price', 'score_service', 'score_innovation')
    def _compute_overall_score(self):
        config = self.env['purchase.intelligence.config'].search([], limit=1)
        # Usar pesos por defecto si no hay configuración
        w_quality = config.weight_quality if config else 25
        w_delivery = config.weight_delivery if config else 25
        w_price = config.weight_price if config else 20
        w_service = config.weight_service if config else 20
        w_innovation = config.weight_innovation if config else 10

        for record in self:
            score = (
                (record.score_quality * w_quality) +
                (record.score_delivery * w_delivery) +
                (record.score_price * w_price) +
                (record.score_service * w_service) +
                (record.score_innovation * w_innovation)
            ) / 100.0
            record.overall_score = score
    
    @api.model
    def action_generate_all_scorecards(self):
        """
        MÉTODO AUTOMÁTICO: Genera evaluaciones para TODOS los proveedores
        basándose en datos REALES del sistema (órdenes, entregas, precios, etc.)
        """
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== Iniciando generación automática de scorecards de proveedores ===")
        
        from datetime import timedelta
        today = fields.Date.context_today(self)
        date_90_days_ago = today - timedelta(days=90)
        
        # Obtener todos los proveedores con órdenes de compra
        suppliers = self.env['res.partner'].search([('supplier_rank', '>', 0)])
        
        created_count = 0
        updated_count = 0
        
        for supplier in suppliers:
            # Verificar si ya existe scorecard este mes
            existing = self.search([
                ('partner_id', '=', supplier.id),
                ('date', '>=', today - timedelta(days=30))
            ], limit=1)
            
            # Obtener órdenes del proveedor en los últimos 90 días
            orders = self.env['purchase.order'].search([
                ('partner_id', '=', supplier.id),
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', date_90_days_ago)
            ])
            
            if not orders:
                # Si no hay órdenes, crear scorecard básico
                score_quality = 7.0
                score_delivery = 7.0
                score_price = 7.0
                score_service = 7.0
                score_innovation = 5.0
            else:
                # === CALCULAR SCORE DE ENTREGA (basado en entregas a tiempo) ===
                on_time = 0
                late = 0
                for order in orders:
                    for picking in order.picking_ids.filtered(lambda p: p.state == 'done'):
                        if picking.date_done and order.date_planned:
                            if picking.date_done.date() <= order.date_planned.date():
                                on_time += 1
                            else:
                                late += 1
                
                total_deliveries = on_time + late
                if total_deliveries > 0:
                    delivery_rate = on_time / total_deliveries
                    score_delivery = min(10, delivery_rate * 10)
                else:
                    score_delivery = 7.0  # Sin datos
                
                # === CALCULAR SCORE DE CALIDAD (basado en devoluciones) ===
                # Buscar devoluciones/rechazos
                returns = self.env['stock.picking'].search([
                    ('partner_id', '=', supplier.id),
                    ('picking_type_id.code', '=', 'outgoing'),  # Devoluciones
                    ('origin', 'ilike', 'Return'),
                    ('date_done', '>=', date_90_days_ago),
                    ('state', '=', 'done')
                ])
                
                total_lines = sum(orders.mapped(lambda o: len(o.order_line)))
                return_count = len(returns)
                
                if total_lines > 0:
                    quality_rate = max(0, 1 - (return_count / total_lines))
                    score_quality = min(10, quality_rate * 10)
                else:
                    score_quality = 8.0  # Sin datos asumimos bueno
                
                # === CALCULAR SCORE DE PRECIO (comparar con precio estándar) ===
                price_variance_sum = 0
                price_count = 0
                for order in orders:
                    for line in order.order_line:
                        if line.product_id.standard_price > 0:
                            variance = (line.price_unit - line.product_id.standard_price) / line.product_id.standard_price
                            price_variance_sum += variance
                            price_count += 1
                
                if price_count > 0:
                    avg_variance = price_variance_sum / price_count
                    # -10% mejor = 10, +10% peor = 6, +20% = 4
                    score_price = min(10, max(1, 8 - (avg_variance * 20)))
                else:
                    score_price = 7.0
                
                # === CALCULAR SCORE DE SERVICIO (basado en comunicación y cantidad de órdenes) ===
                order_count = len(orders)
                avg_order_value = sum(orders.mapped('amount_total')) / order_count if order_count else 0
                
                # Más órdenes = mejor relación
                if order_count >= 10:
                    score_service = 9.0
                elif order_count >= 5:
                    score_service = 8.0
                elif order_count >= 2:
                    score_service = 7.0
                else:
                    score_service = 6.0
                
                # === SCORE DE INNOVACIÓN (basado en variedad de productos) ===
                unique_products = len(set(orders.mapped('order_line.product_id.id')))
                if unique_products >= 20:
                    score_innovation = 9.0
                elif unique_products >= 10:
                    score_innovation = 7.0
                elif unique_products >= 5:
                    score_innovation = 6.0
                else:
                    score_innovation = 5.0
            
            vals = {
                'partner_id': supplier.id,
                'date': today,
                'score_quality': round(score_quality, 1),
                'score_delivery': round(score_delivery, 1),
                'score_price': round(score_price, 1),
                'score_service': round(score_service, 1),
                'score_innovation': round(score_innovation, 1),
            }
            
            if existing:
                existing.write(vals)
                updated_count += 1
            else:
                self.create(vals)
                created_count += 1
        
        _logger.info(f"Scorecards generados: {created_count} nuevos, {updated_count} actualizados")
        return {'created': created_count, 'updated': updated_count}
