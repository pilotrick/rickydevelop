# -*- coding: utf-8 -*-
from odoo import models, fields

class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    active_intelligence = fields.Boolean(
        string='Activar en Inteligencia de Compras',
        default=True,
        help='Si está marcado, este almacén se incluirá en los análisis de inteligencia de compras y en el dashboard kanban de productos.'
    )
