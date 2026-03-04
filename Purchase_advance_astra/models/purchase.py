# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    is_automated = fields.Boolean(string='Es Pedido Automatizado', default=False)
    urgency_level = fields.Selection([
        ('normal', 'Normal'),
        ('high', 'Alto'),
        ('critical', 'Crítico')
    ], string='Nivel de Urgencia', default='normal')

    contract_id = fields.Many2one('pi.contract', string='Contrato Marco')
    savings_estimated = fields.Float(string='Ahorro Estimado', compute='_compute_savings')

    @api.depends('order_line.price_unit')
    def _compute_savings(self):
        for order in self:
            savings = 0.0
            for line in order.order_line:
                # Si hay precio estándar, comparar.
                if line.product_id.standard_price > line.price_unit:
                    savings += (line.product_id.standard_price - line.price_unit) * line.product_qty
            order.savings_estimated = savings

    def button_confirm(self):
        """Override para registrar precios en historial"""
        res = super(PurchaseOrder, self).button_confirm()
        # Registrar precios cuando se confirma la orden
        for order in self:
            self.env['pi.price.history'].record_price_from_po(order)
        return res

    def action_view_price_analysis(self):
        """Abrir análisis de precios para los productos de esta orden"""
        self.ensure_one()
        product_ids = self.order_line.mapped('product_id.id')
        return {
            'type': 'ir.actions.act_window',
            'name': 'Historial de Precios',
            'res_model': 'pi.price.history',
            'view_mode': 'list,graph',
            'domain': [('product_id', 'in', product_ids)],
            'context': {'default_partner_id': self.partner_id.id},
        }

    # === INTELIGENCIA AGREGADA ===
    all_warehouse_intelligence_ids = fields.Many2many(
        'pi.product.warehouse.intelligence',
        string='Inteligencia de Stock (Todos)',
        compute='_compute_all_warehouse_intelligence'
    )

    @api.depends('order_line.product_id')
    def _compute_all_warehouse_intelligence(self):
        for order in self:
            products = order.order_line.mapped('product_id.product_tmpl_id')
            order.all_warehouse_intelligence_ids = products.mapped('warehouse_intelligence_ids')

class PIContract(models.Model):
    _name = 'pi.contract'
    _description = 'Contrato de Compra'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Referencia Contrato', required=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    start_date = fields.Date(string='Fecha Inicio')
    end_date = fields.Date(string='Fecha Fin')
    contract_type = fields.Selection([
        ('volume', 'Compromiso de Volumen'),
        ('blanket', 'Pedido Abierto'),
        ('rate', 'Contrato de Tarifa')
    ], string='Tipo de Contrato')

    total_value = fields.Float(string='Valor Total Comprometido')
    utilized_value = fields.Float(string='Valor Utilizado', compute='_compute_utilization', store=True)
    utilization_percentage = fields.Float(string='Porcentaje de Utilización', compute='_compute_utilization', store=True)
    status = fields.Selection([
        ('active', 'Activo'),
        ('expired', 'Vencido'),
        ('pending', 'Pendiente')
    ], string='Estado', default='active')

    @api.depends('partner_id', 'start_date', 'end_date')
    def _compute_utilization(self):
        """Calcular utilización del contrato basado en órdenes de compra"""
        for contract in self:
            if not contract.partner_id or not contract.start_date:
                contract.utilized_value = 0.0
                contract.utilization_percentage = 0.0
                continue
            
            # Buscar órdenes de compra del proveedor en el período del contrato
            domain = [
                ('partner_id', '=', contract.partner_id.id),
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', contract.start_date)
            ]
            if contract.end_date:
                domain.append(('date_order', '<=', contract.end_date))
            
            orders = self.env['purchase.order'].search(domain)
            utilized = sum(orders.mapped('amount_total'))
            
            contract.utilized_value = utilized
            if contract.total_value > 0:
                contract.utilization_percentage = (utilized / contract.total_value) * 100
            else:
                contract.utilization_percentage = 0.0


