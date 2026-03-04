# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta

class PIForecastAccuracy(models.Model):
    _name = 'pi.forecast.accuracy'
    _description = 'Precisión de Pronósticos'
    _order = 'date desc'
    
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    date = fields.Date(string='Fecha de Evaluación', default=fields.Date.context_today)
    
    forecast_id = fields.Many2one('purchase.intelligence.forecast', string='Pronóstico')
    forecasted_qty = fields.Float(string='Cantidad Pronosticada')
    actual_qty = fields.Float(string='Cantidad Real')
    
    accuracy_percent = fields.Float(string='Precisión (%)', compute='_compute_accuracy', store=True)
    error_absolute = fields.Float(string='Error Absoluto', compute='_compute_accuracy', store=True)
    error_percent = fields.Float(string='Error (%)', compute='_compute_accuracy', store=True)
    
    method = fields.Selection([
        ('time_series', 'Series Temporales'),
        ('machine_learning', 'Aprendizaje Automático'),
        ('manual', 'Ajuste Manual')
    ], string='Método Usado')
    
    @api.depends('forecasted_qty', 'actual_qty')
    def _compute_accuracy(self):
        for record in self:
            if record.forecasted_qty and record.actual_qty:
                error = abs(record.forecasted_qty - record.actual_qty)
                record.error_absolute = error
                record.error_percent = (error / record.actual_qty * 100) if record.actual_qty else 0
                record.accuracy_percent = 100 - record.error_percent
            else:
                record.error_absolute = 0
                record.error_percent = 0
                record.accuracy_percent = 0


class PIRiskAssessment(models.Model):
    _name = 'pi.risk.assessment'
    _description = 'Evaluación de Riesgos'
    _order = 'risk_score desc, date desc'
    
    name = fields.Char(string='Descripción del Riesgo', required=True)
    date = fields.Date(string='Fecha de Evaluación', default=fields.Date.context_today)
    
    risk_type = fields.Selection([
        ('supplier', 'Riesgo de Proveedor'),
        ('geographic', 'Riesgo Geográfico'),
        ('market', 'Riesgo de Mercado'),
        ('operational', 'Riesgo Operacional'),
        ('compliance', 'Riesgo de Cumplimiento'),
        ('financial', 'Riesgo Financiero')
    ], string='Tipo de Riesgo', required=True)
    
    partner_id = fields.Many2one('res.partner', string='Proveedor Relacionado')
    product_id = fields.Many2one('product.product', string='Producto Relacionado')
    
    # Scoring
    probability = fields.Selection([
        ('1', 'Muy Baja (10%)'),
        ('2', 'Baja (25%)'),
        ('3', 'Media (50%)'),
        ('4', 'Alta (75%)'),
        ('5', 'Muy Alta (90%)')
    ], string='Probabilidad', required=True, default='3')
    
    impact = fields.Selection([
        ('1', 'Insignificante'),
        ('2', 'Menor'),
        ('3', 'Moderado'),
        ('4', 'Mayor'),
        ('5', 'Crítico')
    ], string='Impacto', required=True, default='3')
    
    risk_score = fields.Integer(string='Puntuación de Riesgo', compute='_compute_risk_score', store=True)
    risk_level = fields.Selection([
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', 'Crítico')
    ], string='Nivel de Riesgo', compute='_compute_risk_score', store=True)
    
    # Mitigación
    mitigation_plan = fields.Text(string='Plan de Mitigación')
    mitigation_status = fields.Selection([
        ('none', 'Sin Plan'),
        ('planned', 'Planificado'),
        ('in_progress', 'En Progreso'),
        ('completed', 'Completado')
    ], string='Estado de Mitigación', default='none')
    
    responsible_id = fields.Many2one('res.users', string='Responsable')
    
    state = fields.Selection([
        ('identified', 'Identificado'),
        ('assessed', 'Evaluado'),
        ('mitigating', 'En Mitigación'),
        ('monitored', 'Monitoreado'),
        ('closed', 'Cerrado')
    ], string='Estado', default='identified')
    
    @api.depends('probability', 'impact')
    def _compute_risk_score(self):
        for record in self:
            prob = int(record.probability) if record.probability else 0
            imp = int(record.impact) if record.impact else 0
            score = prob * imp
            record.risk_score = score
            
            if score <= 6:
                record.risk_level = 'low'
            elif score <= 12:
                record.risk_level = 'medium'
            elif score <= 20:
                record.risk_level = 'high'
            else:
                record.risk_level = 'critical'
    
    @api.model
    def assess_supplier_risks(self):
        """
        Método para evaluar riesgos de proveedores automáticamente
        """
        suppliers = self.env['res.partner'].search([('supplier_rank', '>', 0)])
        
        for supplier in suppliers:
            # Evaluar riesgo financiero basado en score
            if supplier.supplier_score < 6.0:
                existing = self.search([
                    ('partner_id', '=', supplier.id),
                    ('risk_type', '=', 'supplier'),
                    ('state', 'not in', ['closed'])
                ], limit=1)
                
                if not existing:
                    self.create({
                        'name': f'Bajo rendimiento de proveedor: {supplier.name}',
                        'risk_type': 'supplier',
                        'partner_id': supplier.id,
                        'probability': '4',
                        'impact': '4',
                        'mitigation_plan': 'Buscar proveedores alternativos y renegociar términos.',
                        'state': 'identified',
                    })
            
            # Evaluar concentración de gasto
            total_spend = sum(self.env['purchase.order'].search([
                ('partner_id', '=', supplier.id),
                ('state', 'in', ['purchase', 'done'])
            ]).mapped('amount_total'))
            
            if total_spend > 1000000:  # Más de 1M
                existing = self.search([
                    ('partner_id', '=', supplier.id),
                    ('risk_type', '=', 'financial'),
                    ('state', 'not in', ['closed'])
                ], limit=1)
                
                if not existing:
                    self.create({
                        'name': f'Alta concentración de gasto: {supplier.name}',
                        'risk_type': 'financial',
                        'partner_id': supplier.id,
                        'probability': '3',
                        'impact': '5',
                        'mitigation_plan': 'Diversificar proveedores para esta categoría.',
                        'state': 'identified',
                    })
        
        return True
