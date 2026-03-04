# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PISavingsTracker(models.Model):
    _name = 'pi.savings.tracker'
    _description = 'Rastreador de Ahorros de Compras'

    name = fields.Char(string='Descripción del Ahorro', required=True)
    date = fields.Date(string='Fecha', default=fields.Date.context_today)
    category_id = fields.Many2one('product.category', string='Categoría')

    savings_type = fields.Selection([
        ('negotiation', 'Negociación'),
        ('volume', 'Descuento por Volumen'),
        ('process', 'Mejora de Proceso'),
        ('alternative', 'Sourcing Alternativo'),
        ('market', 'Bajada de Mercado')
    ], string='Tipo de Ahorro')

    amount_estimated = fields.Float(string='Monto Estimado')
    amount_captured = fields.Float(string='Monto Capturado')
    status = fields.Selection([
        ('identified', 'Identificado'),
        ('realized', 'Realizado'),
        ('cancelled', 'Cancelado')
    ], default='identified')
