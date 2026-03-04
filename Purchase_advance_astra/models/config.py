# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PurchaseIntelligenceConfig(models.Model):
    _name = 'purchase.intelligence.config'
    _description = 'Configuración de Inteligencia de Compras'

    name = fields.Char(string='Nombre', required=True)
    active = fields.Boolean(default=True)

    # Configuraciones Globales
    service_level_target = fields.Float(string='Nivel de Servicio Objetivo (%)', default=95.0)
    holding_cost_percentage = fields.Float(string='Costo Anual de Mantenimiento (%)', default=20.0)
    ordering_cost = fields.Float(string='Costo por Pedido', default=50.0)

    # Ponderaciones para Cuadro de Mando de Proveedores
    weight_quality = fields.Float(string='Peso Calidad (%)', default=30.0)
    weight_delivery = fields.Float(string='Peso Entrega (%)', default=25.0)
    weight_price = fields.Float(string='Peso Precio (%)', default=20.0)
    weight_service = fields.Float(string='Peso Servicio (%)', default=15.0)
    weight_innovation = fields.Float(string='Peso Innovación (%)', default=10.0)

    @api.constrains('weight_quality', 'weight_delivery', 'weight_price', 'weight_service', 'weight_innovation')
    def _check_weights(self):
        for record in self:
            total = record.weight_quality + record.weight_delivery + record.weight_price + record.weight_service + record.weight_innovation
            if abs(total - 100.0) > 0.01:
                # Se podría lanzar una advertencia o error de validación
                pass
