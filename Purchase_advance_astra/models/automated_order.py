# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo 19 - Purchase Intelligence Module
#    Copyright (C) 2024
#    @author: Your Name
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging
from datetime import datetime, timedelta
import json

_logger = logging.getLogger(__name__)


class PurchaseIntelligenceAutomatedOrder(models.Model):
    _inherit = 'pi.automated.order'
    
    # Campos adicionales para soporte multi-almacén
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén Destino',
        required=True,
        help="Almacén específico para esta orden automatizada"
    )
    
    warehouse_stock_level = fields.Float(
        string='Nivel de Stock en Almacén',
        digits='Product Unit of Measure',
        help="Cantidad actual del producto en el almacén especificado"
    )
    
    warehouse_reorder_point = fields.Float(
        string='Punto de Reorden del Almacén',
        digits='Product Unit of Measure',
        help="Punto de reorden específico para este almacén"
    )
    
    warehouse_safety_stock = fields.Float(
        string='Stock de Seguridad del Almacén',
        digits='Product Unit of Measure',
        help="Stock de seguridad específico para este almacén"
    )
    
    warehouse_daily_usage = fields.Float(
        string='Uso Diario del Almacén',
        digits='Product Unit of Measure',
        help="Consumo diario promedio en este almacén"
    )
    
    warehouse_days_of_stock = fields.Float(
        string='Días de Stock en Almacén',
        digits=(10, 2),
        help="Días de stock disponibles en este almacén"
    )
    
    warehouse_urgency_level = fields.Selection([
        ('critical', '🔴 Crítico'),
        ('high', '🟠 Alto'),
        ('medium', '🟡 Medio'),
        ('low', '🟢 Bajo'),
    ], string='Nivel de Urgencia por Almacén', default='medium')
    
    warehouse_priority_score = fields.Float(
        string='Score de Prioridad del Almacén',
        digits=(5, 2),
        help="Puntuación de prioridad basada en condiciones específicas del almacén"
    )
    
    is_warehouse_specific = fields.Boolean(
        string='Es Específico de Almacén',
        default=True,
        help="Indica si esta orden es específica para un almacén"
    )
    
    @api.depends('warehouse_id', 'product_id')
    def _compute_warehouse_metrics(self):
        """
        Calcular métricas específicas del almacén para la orden automatizada
        """
        for record in self:
            if not record.warehouse_id or not record.product_id:
                continue
            
            # Obtener stock actual en el almacén
            record.warehouse_stock_level = record._get_warehouse_stock_level()
            
            # Obtener punto de reorden específico del almacén
            record.warehouse_reorder_point = record._get_warehouse_reorder_point()
            
            # Obtener stock de seguridad específico del almacén
            record.warehouse_safety_stock = record._get_warehouse_safety_stock()
            
            # Calcular uso diario en el almacén
            record.warehouse_daily_usage = record._get_warehouse_daily_usage()
            
            # Calcular días de stock
            if record.warehouse_daily_usage > 0:
                record.warehouse_days_of_stock = record.warehouse_stock_level / record.warehouse_daily_usage
            else:
                record.warehouse_days_of_stock = 999  # Infinito si no hay uso
            
            # Calcular nivel de urgencia
            record._compute_warehouse_urgency()
            
            # Calcular score de prioridad
            record._compute_warehouse_priority_score()
    
    def _get_warehouse_stock_level(self):
        """
        Obtener el nivel de stock actual del producto en el almacén
        """
        if not self.warehouse_id or not self.product_id:
            return 0
        
        # Buscar stock en las ubicaciones del almacén
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id.warehouse_id', '=', self.warehouse_id.id),
            ('quantity', '>', 0)
        ])
        
        return sum(quant.quantity for quant in quants)
    
    def _get_warehouse_reorder_point(self):
        """
        Obtener el punto de reorden específico del almacén
        """
        if not self.warehouse_id or not self.product_id:
            return 0
        
        # Buscar regla de reorden específica del almacén
        reorder_rule = self.env['stock.warehouse.orderpoint'].search([
            ('product_id', '=', self.product_id.id),
            ('warehouse_id', '=', self.warehouse_id.id),
            ('active', '=', True)
        ], limit=1)
        
        if reorder_rule:
            return reorder_rule.product_min_qty
        
        # Si no hay regla específica, usar la del producto con ajuste de almacén
        if self.product_id.reorder_point:
            warehouse_factor = self._get_warehouse_adjustment_factor()
            return self.product_id.reorder_point * warehouse_factor
        
        return 0
    
    def _get_warehouse_safety_stock(self):
        """
        Obtener el stock de seguridad específico del almacén
        """
        if not self.warehouse_id or not self.product_id:
            return 0
        
        # Buscar regla de reorden específica del almacén
        reorder_rule = self.env['stock.warehouse.orderpoint'].search([
            ('product_id', '=', self.product_id.id),
            ('warehouse_id', '=', self.warehouse_id.id),
            ('active', '=', True)
        ], limit=1)
        
        if reorder_rule:
            return reorder_rule.product_max_qty - reorder_rule.product_min_qty
        
        # Si no hay regla específica, usar la del producto con ajuste de almacén
        if self.product_id.safety_stock:
            warehouse_factor = self._get_warehouse_adjustment_factor()
            return self.product_id.safety_stock * warehouse_factor
        
        return 0
    
    def _get_warehouse_daily_usage(self):
        """
        Calcular el uso diario del producto en el almacén específico
        """
        if not self.warehouse_id or not self.product_id:
            return 0
        
        # Buscar movimientos de salida en los últimos 30 días
        date_from = fields.Date.today() - timedelta(days=30)
        
        moves_out = self.env['stock.move'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id.warehouse_id', '=', self.warehouse_id.id),
            ('location_dest_id.usage', '!=', 'internal'),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        total_qty = sum(move.product_uom_qty for move in moves_out)
        return total_qty / 30  # Promedio diario
    
    def _get_warehouse_adjustment_factor(self):
        """
        Obtener factor de ajuste específico para el tipo de almacén
        """
        if not self.warehouse_id:
            return 1.0
        
        # Factores de ajuste según tipo de almacén
        warehouse_factors = {
            'main_warehouse': 1.2,      # Mayor stock en almacén principal
            'secondary_warehouse': 1.0,  # Stock estándar
            'regional_warehouse': 0.8,   # Menor stock en almacenes regionales
            'virtual_warehouse': 0.0,    # No mantener stock virtual
        }
        
        return warehouse_factors.get(getattr(self.warehouse_id, 'warehouse_type', None), 1.0)
    
    def _compute_warehouse_urgency(self):
        """
        Calcular el nivel de urgencia basado en condiciones del almacén
        """
        if not self.warehouse_id or not self.product_id:
            self.warehouse_urgency_level = 'medium'
            return
        
        # Si no hay stock, es crítico
        if self.warehouse_stock_level <= 0:
            self.warehouse_urgency_level = 'critical'
            return
        
        # Si está por debajo del punto de reorden, es alto
        if self.warehouse_stock_level <= self.warehouse_reorder_point:
            self.warehouse_urgency_level = 'high'
            return
        
        # Si tiene menos de 7 días de stock, es medio
        if self.warehouse_days_of_stock <= 7:
            self.warehouse_urgency_level = 'medium'
            return
        
        # Si tiene menos de 14 días de stock, es bajo
        if self.warehouse_days_of_stock <= 14:
            self.warehouse_urgency_level = 'low'
            return
        
        # Si tiene más de 14 días, no es urgente
        self.warehouse_urgency_level = 'low'
    
    def _compute_warehouse_priority_score(self):
        """
        Calcular score de prioridad basado en múltiples factores del almacén
        """
        if not self.warehouse_id or not self.product_id:
            self.warehouse_priority_score = 50.0  # Neutral
            return
        
        score = 50.0  # Base
        
        # Factor de urgencia de stock (-30 a +30)
        if self.warehouse_days_of_stock <= 0:
            score += 30
        elif self.warehouse_days_of_stock <= 3:
            score += 20
        elif self.warehouse_days_of_stock <= 7:
            score += 10
        elif self.warehouse_days_of_stock <= 14:
            score += 5
        else:
            score -= 10  # Reducir prioridad si hay mucho stock
        
        # Factor de valor del producto (-10 a +20)
        if self.product_id.standard_price:
            if self.product_id.standard_price > 1000:
                score += 20  # Productos caros tienen mayor prioridad
            elif self.product_id.standard_price > 100:
                score += 10
            elif self.product_id.standard_price < 10:
                score -= 5   # Productos baratos tienen menor prioridad
        
        # Factor de criticidad del producto (-10 a +15)
        if hasattr(self.product_id, 'abc_classification'):
            if self.product_id.abc_classification == 'A':
                score += 15
            elif self.product_id.abc_classification == 'B':
                score += 5
            elif self.product_id.abc_classification == 'C':
                score -= 5
        
        # Factor de tipo de almacén (-5 a +10)
        warehouse_type_scores = {
            'main_warehouse': 10,
            'secondary_warehouse': 5,
            'regional_warehouse': 0,
            'virtual_warehouse': -5,
        }
        score += warehouse_type_scores.get(getattr(self.warehouse_id, 'warehouse_type', None) or 'main_warehouse', 0)
        
        # Asegurar que el score esté entre 0 y 100
        self.warehouse_priority_score = max(0, min(100, score))
    
    @api.model
    def generate_warehouse_automated_orders(self, warehouse_id=None):
        """
        Generar órdenes automatizadas específicas para un almacén o todos los almacenes
        """
        if warehouse_id:
            warehouses = self.env['stock.warehouse'].browse(warehouse_id)
        else:
            warehouses = self.env['stock.warehouse'].search([])
        
        generated_orders = []
        
        for warehouse in warehouses:
            # Obtener productos que necesitan reorden en este almacén
            products_needing_reorder = self._get_products_needing_reorder_warehouse(warehouse)
            
            for product_data in products_needing_reorder:
                # Crear orden automatizada para este almacén
                order = self.create({
                    'product_id': product_data['product_id'],
                    'warehouse_id': warehouse.id,
                    'suggested_qty': product_data['suggested_qty'],
                    'urgency_level': product_data['urgency_level'],
                    'reason': product_data['reason'],
                    'estimated_cost': product_data['estimated_cost'],
                    'auto_generated': True,
                })
                
                # Calcular métricas específicas del almacén
                order._compute_warehouse_metrics()
                
                generated_orders.append(order)
        
        return generated_orders
    
    def _get_products_needing_reorder_warehouse(self, warehouse):
        """
        Obtener productos que necesitan reorden en un almacén específico
        """
        products_needing_reorder = []
        
        # Buscar todos los productos de tipo producto
        products = self.env['product.template'].search([('type', '=', 'product')])
        
        for product in products:
            # Obtener stock actual en el almacén
            stock_level = self._get_product_stock_warehouse(product, warehouse)
            
            # Obtener punto de reorden específico del almacén
            reorder_point = self._get_product_reorder_point_warehouse(product, warehouse)
            
            # Obtener stock de seguridad específico del almacén
            safety_stock = self._get_product_safety_stock_warehouse(product, warehouse)
            
            # Obtener uso diario en el almacén
            daily_usage = self._get_product_daily_usage_warehouse(product, warehouse)
            
            # Determinar si necesita reorden
            needs_reorder, urgency_level, reason = self._evaluate_reorder_need(
                stock_level, reorder_point, safety_stock, daily_usage
            )
            
            if needs_reorder:
                # Calcular cantidad sugerida
                suggested_qty = self._calculate_suggested_qty(
                    stock_level, reorder_point, safety_stock, daily_usage, product
                )
                
                # Calcular costo estimado
                estimated_cost = suggested_qty * product.standard_price
                
                products_needing_reorder.append({
                    'product_id': product.id,
                    'stock_level': stock_level,
                    'reorder_point': reorder_point,
                    'safety_stock': safety_stock,
                    'daily_usage': daily_usage,
                    'suggested_qty': suggested_qty,
                    'urgency_level': urgency_level,
                    'reason': reason,
                    'estimated_cost': estimated_cost,
                })
        
        # Ordenar por urgencia y prioridad
        products_needing_reorder.sort(
            key=lambda x: (x['urgency_level'], x['estimated_cost']), 
            reverse=True
        )
        
        return products_needing_reorder
    
    def _get_product_stock_warehouse(self, product, warehouse):
        """
        Obtener stock de un producto en un almacén específico
        """
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product.id),
            ('location_id.warehouse_id', '=', warehouse.id),
            ('quantity', '>', 0)
        ])
        
        return sum(quant.quantity for quant in quants)
    
    def _get_product_reorder_point_warehouse(self, product, warehouse):
        """
        Obtener punto de reorden de un producto en un almacén específico
        """
        # Buscar regla de reorden específica del almacén
        reorder_rule = self.env['stock.warehouse.orderpoint'].search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
            ('active', '=', True)
        ], limit=1)
        
        if reorder_rule:
            return reorder_rule.product_min_qty
        
        # Usar punto de reorden del producto con ajuste de almacén
        if product.reorder_point:
            warehouse_factor = self._get_warehouse_adjustment_factor_for_type(getattr(warehouse, "warehouse_type", None))
            return product.reorder_point * warehouse_factor
        
        return 0
    
    def _get_product_safety_stock_warehouse(self, product, warehouse):
        """
        Obtener stock de seguridad de un producto en un almacén específico
        """
        # Buscar regla de reorden específica del almacén
        reorder_rule = self.env['stock.warehouse.orderpoint'].search([
            ('product_id', '=', product.id),
            ('warehouse_id', '=', warehouse.id),
            ('active', '=', True)
        ], limit=1)
        
        if reorder_rule:
            return reorder_rule.product_max_qty - reorder_rule.product_min_qty
        
        # Usar stock de seguridad del producto con ajuste de almacén
        if product.safety_stock:
            warehouse_factor = self._get_warehouse_adjustment_factor_for_type(getattr(warehouse, "warehouse_type", None))
            return product.safety_stock * warehouse_factor
        
        return 0
    
    def _get_product_daily_usage_warehouse(self, product, warehouse):
        """
        Obtener uso diario de un producto en un almacén específico
        """
        date_from = fields.Date.today() - timedelta(days=30)
        
        moves_out = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('location_id.warehouse_id', '=', warehouse.id),
            ('location_dest_id.usage', '!=', 'internal'),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        total_qty = sum(move.product_uom_qty for move in moves_out)
        return total_qty / 30  # Promedio diario
    
    def _get_warehouse_adjustment_factor_for_type(self, warehouse_type):
        """
        Obtener factor de ajuste según tipo de almacén
        """
        warehouse_factors = {
            'main_warehouse': 1.2,
            'secondary_warehouse': 1.0,
            'regional_warehouse': 0.8,
            'virtual_warehouse': 0.0,
        }
        
        return warehouse_factors.get(warehouse_type, 1.0)
    
    def _evaluate_reorder_need(self, stock_level, reorder_point, safety_stock, daily_usage):
        """
        Evaluar si un producto necesita reorden
        """
        # Si no hay stock, es crítico
        if stock_level <= 0:
            return True, 'critical', 'Sin stock disponible'
        
        # Si está por debajo del stock de seguridad, es crítico
        if stock_level <= safety_stock:
            return True, 'critical', f'Stock ({stock_level}) por debajo del stock de seguridad ({safety_stock})'
        
        # Si está por debajo del punto de reorden, es alto
        if stock_level <= reorder_point:
            return True, 'high', f'Stock ({stock_level}) por debajo del punto de reorden ({reorder_point})'
        
        # Si hay poco consumo pero stock bajo, es medio
        if daily_usage > 0 and stock_level / daily_usage <= 7:
            return True, 'medium', f'Stock para {stock_level/daily_usage:.1f} días'
        
        return False, 'low', 'Stock adecuado'
    
    def _calculate_suggested_qty(self, stock_level, reorder_point, safety_stock, daily_usage, product):
        """
        Calcular cantidad sugerida para reorden
        """
        # Base: cantidad para llegar al punto de reorden + stock de seguridad
        base_quantity = (reorder_point + safety_stock) - stock_level
        
        # Ajustar por consumo diario (30 días de stock)
        if daily_usage > 0:
            consumption_adjustment = daily_usage * 30
            base_quantity = max(base_quantity, consumption_adjustment)
        
        # Ajustar por EOQ si está disponible
        if hasattr(product, 'eoq') and product.eoq > 0:
            # Redondear hacia arriba al múltiplo más cercano del EOQ
            eoq_multiplier = max(1, int(base_quantity / product.eoq) + 1)
            base_quantity = eoq_multiplier * product.eoq
        
        # Ajustar por cantidad mínima de compra
        if hasattr(product, 'min_order_qty') and product.min_order_qty > 0:
            base_quantity = max(base_quantity, product.min_order_qty)
        
        # Ajustar por cantidad múltiple de compra
        if hasattr(product, 'order_multiple') and product.order_multiple > 0:
            multiple = product.order_multiple
            base_quantity = int(base_quantity / multiple) * multiple
            if base_quantity == 0:
                base_quantity = multiple
        
        return max(0, base_quantity)
    
    def action_create_purchase_order_warehouse(self):
        """
        Crear orden de compra específica para el almacén
        """
        if not self.warehouse_id:
            raise UserError(_("Debe especificar un almacén para crear la orden de compra."))
        
        # Buscar o crear proveedor para el producto
        supplier = self.product_id.seller_ids[:1].partner_id if self.product_id.seller_ids else None
        
        if not supplier:
            raise UserError(_("El producto no tiene proveedor configurado."))
        
        # Obtener tipo de operación de compra para este almacén
        picking_type = self.env['stock.picking.type'].search([
            ('warehouse_id', '=', self.warehouse_id.id),
            ('code', '=', 'incoming')
        ], limit=1)
        
        if not picking_type:
            raise UserError(_("No se encontró tipo de operación de compra para este almacén."))
        
        # Crear orden de compra
        purchase_order = self.env['purchase.order'].create({
            'partner_id': supplier.id,
            'picking_type_id': picking_type.id,
            'origin': f'Automated Order - Warehouse {self.warehouse_id.name}',
            'notes': f'Orden automatizada generada para almacén {self.warehouse_id.name}\n'
                    f'Razón: {self.reason}\n'
                    f'Urgencia: {self.urgency_level}',
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.suggested_qty,
                'price_unit': self.product_id.standard_price,
                'name': self.product_id.name,
                'date_planned': fields.Datetime.now() + timedelta(days=7),
            })],
        })
        
        # Actualizar estado de la orden automatizada
        self.write({
            'status': 'order_created',
            'purchase_order_id': purchase_order.id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Orden de Compra Creada',
            'res_model': 'purchase.order',
            'res_id': purchase_order.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.model
    def action_generate_warehouse_orders_cron(self):
        """
        Tarea programada para generar órdenes automatizadas por almacén
        """
        _logger.info("Generando órdenes automatizadas por almacén...")
        
        try:
            generated_orders = self.generate_warehouse_automated_orders()
            _logger.info(f"Se generaron {len(generated_orders)} órdenes automatizadas")
            return True
            
        except Exception as e:
            _logger.error(f"Error generando órdenes automatizadas: {e}")
            return False