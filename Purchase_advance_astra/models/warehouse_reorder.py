# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PIWarehouseReorderOptimization(models.Model):
    _name = 'pi.warehouse.reorder.optimization'
    _description = 'Optimización de Reorden por Almacén'
    _order = 'date desc, warehouse_id, product_id'
    
    # Identificadores
    product_id = fields.Many2one('product.product', string='Producto', required=True, index=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True, index=True)
    date = fields.Date(string='Fecha de Análisis', default=fields.Date.context_today, required=True, index=True)
    
    # Stock específico del almacén
    warehouse_stock = fields.Float(string='Stock en Almacén', help='Stock disponible en este almacén específico')
    warehouse_virtual_stock = fields.Float(string='Stock Virtual', help='Stock disponible + entrante - saliente')
    incoming_qty = fields.Float(string='Cantidad Entrante', help='Cantidad en órdenes de compra confirmadas')
    outgoing_qty = fields.Float(string='Cantidad Saliente', help='Cantidad en órdenes de venta confirmadas')
    
    # Parámetros actuales del almacén
    current_rop = fields.Float(string='ROP Actual')
    current_eoq = fields.Float(string='EOQ Actual')
    current_safety_stock = fields.Float(string='Stock de Seguridad Actual')
    
    # Parámetros optimizados para este almacén
    optimized_rop = fields.Float(string='ROP Optimizado', help='Punto de Reorden Optimizado para este almacén')
    optimized_eoq = fields.Float(string='EOQ Optimizado', help='Cantidad Económica de Pedido Optimizada')
    optimized_safety_stock = fields.Float(string='Stock de Seguridad Optimizado')
    
    # Métricas específicas del almacén
    daily_usage_warehouse = fields.Float(string='Consumo Diario en Almacén', help='Consumo diario promedio en este almacén')
    lead_time_days = fields.Integer(string='Tiempo de Entrega (Días)', help='Días de entrega a este almacén')
    days_of_stock = fields.Float(string='Días de Stock', compute='_compute_days_of_stock', store=True)
    
    # Riesgos y costos
    stockout_risk = fields.Float(string='Riesgo de Rotura (%)', help='Probabilidad de quedarse sin stock')
    carrying_cost = fields.Float(string='Costo de Mantenimiento', help='Costo mensual de mantener inventario')
    ordering_cost = fields.Float(string='Costo de Pedido', help='Costo mensual de realizar pedidos')
    total_cost = fields.Float(string='Costo Total', help='Costo total mensual de inventario')
    
    # Análisis de demanda
    demand_variability = fields.Float(string='Variabilidad de Demanda (%)', help='Desviación estándar de la demanda')
    service_level = fields.Float(string='Nivel de Servicio (%)', default=95.0, help='Nivel de servicio objetivo')
    
    # Recomendaciones
    recommendation = fields.Text(string='Recomendación')
    priority = fields.Selection([
        ('low', 'Baja'),
        ('medium', 'Media'),
        ('high', 'Alta'),
        ('critical', 'Crítica')
    ], string='Prioridad', compute='_compute_priority', store=True)
    
    applied = fields.Boolean(string='Aplicado', default=False)
    
    # Campos relacionales para análisis
    product_name = fields.Char(related='product_id.name', string='Nombre Producto', store=True)
    product_category = fields.Many2one(related='product_id.categ_id', string='Categoría', store=True)
    warehouse_name = fields.Char(related='warehouse_id.name', string='Nombre Almacén', store=True)
    
    @api.depends('warehouse_stock', 'daily_usage_warehouse')
    def _compute_days_of_stock(self):
        """Calcular días de stock disponibles en el almacén"""
        for record in self:
            if record.daily_usage_warehouse > 0:
                record.days_of_stock = record.warehouse_stock / record.daily_usage_warehouse
            else:
                record.days_of_stock = 999
    
    @api.depends('stockout_risk', 'days_of_stock', 'warehouse_stock', 'optimized_rop')
    def _compute_priority(self):
        """Calcular prioridad basada en riesgo y stock"""
        for record in self:
            if record.warehouse_stock <= 0 or record.stockout_risk >= 80:
                record.priority = 'critical'
            elif record.days_of_stock < record.lead_time_days or record.stockout_risk >= 50:
                record.priority = 'high'
            elif record.warehouse_stock < record.optimized_rop or record.stockout_risk >= 25:
                record.priority = 'medium'
            else:
                record.priority = 'low'
    
    @api.model
    def action_generate_warehouse_optimizations(self):
        """
        MÉTODO AUTOMÁTICO: Genera optimizaciones de reorden para TODOS los productos
        en TODOS los almacenes usando los datos reales del sistema
        """
        _logger.info("=== Iniciando generación de optimizaciones por almacén ===")
        
        warehouses = self.env['stock.warehouse'].search([])
        products = self.env['product.product'].search([
            ('is_storable', '=', True),
            ('purchase_ok', '=', True)
        ])
        
        today = fields.Date.context_today(self)
        created_count = 0
        updated_count = 0
        
        for warehouse in warehouses:
            location = warehouse.lot_stock_id
            
            for product in products:
                # Buscar optimización existente reciente
                existing = self.search([
                    ('product_id', '=', product.id),
                    ('warehouse_id', '=', warehouse.id),
                    ('date', '>=', today - timedelta(days=2))
                ], limit=1)
                
                # Obtener stock del almacén específico
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', '=', location.id)
                ])
                warehouse_stock = sum(stock_quant.mapped('quantity'))
                
                # Calcular stock virtual (disponible + entrante - saliente)
                incoming = self._get_incoming_qty(product, warehouse)
                outgoing = self._get_outgoing_qty(product, warehouse)
                virtual_stock = warehouse_stock + incoming - outgoing
                
                # Calcular consumo diario en este almacén
                daily_usage = self._calculate_warehouse_daily_usage(product, warehouse)
                
                # Obtener tiempo de entrega
                lead_time = product.lead_time_days or 7
                
                # Calcular parámetros optimizados
                optimization_data = self._calculate_optimization_params(
                    product, warehouse, warehouse_stock, daily_usage, lead_time
                )
                
                vals = {
                    'product_id': product.id,
                    'warehouse_id': warehouse.id,
                    'date': today,
                    'warehouse_stock': warehouse_stock,
                    'warehouse_virtual_stock': virtual_stock,
                    'incoming_qty': incoming,
                    'outgoing_qty': outgoing,
                    'daily_usage_warehouse': daily_usage,
                    'lead_time_days': lead_time,
                    **optimization_data
                }
                
                if existing:
                    existing.write(vals)
                    updated_count += 1
                else:
                    self.create(vals)
                    created_count += 1
        
        _logger.info(f"Optimizaciones por almacén: {created_count} nuevas, {updated_count} actualizadas")
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '✅ Optimización por Almacén Completada',
                'message': f'Se generaron {created_count} nuevas optimizaciones y se actualizaron {updated_count} para {len(warehouses)} almacenes.',
                'type': 'success',
                'sticky': False,
            }
        }
    
    def _get_incoming_qty(self, product, warehouse):
        """Obtener cantidad entrante de órdenes de compra confirmadas"""
        po_lines = self.env['purchase.order.line'].search([
            ('product_id', '=', product.id),
            ('order_id.state', 'in', ['purchase', 'done']),
            ('order_id.picking_type_id.warehouse_id', '=', warehouse.id)
        ])
        return sum(po_lines.mapped('product_qty')) - sum(po_lines.mapped('qty_received'))
    
    def _get_outgoing_qty(self, product, warehouse):
        """Obtener cantidad saliente de órdenes de venta confirmadas"""
        so_lines = self.env['sale.order.line'].search([
            ('product_id', '=', product.id),
            ('order_id.state', 'in', ['sale', 'done']),
            ('order_id.warehouse_id', '=', warehouse.id)
        ])
        return sum(so_lines.mapped('product_uom_qty')) - sum(so_lines.mapped('qty_delivered'))
    
    def _calculate_warehouse_daily_usage(self, product, warehouse):
        """Calcular consumo diario promedio en el almacén específico"""
        # Buscar movimientos de salida de los últimos 90 días
        ninety_days_ago = fields.Date.context_today(self) - timedelta(days=90)
        
        moves = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('location_id', '=', warehouse.lot_stock_id.id),
            ('date', '>=', ninety_days_ago),
            ('state', '=', 'done')
        ])
        
        total_qty = sum(moves.mapped('product_uom_qty'))
        daily_usage = total_qty / 90 if total_qty > 0 else 0
        
        return daily_usage
    
    def _calculate_optimization_params(self, product, warehouse, current_stock, daily_usage, lead_time):
        """Calcular parámetros de optimización para el almacén"""
        
        # Calcular ROP (Reorder Point) = Demanda durante lead time + Safety Stock
        avg_demand = daily_usage * lead_time
        safety_factor = 1.65  # 95% nivel de servicio
        
        # Variabilidad de demanda (20% del consumo promedio)
        demand_std = daily_usage * 0.20
        demand_variability = (demand_std / daily_usage * 100) if daily_usage > 0 else 0
        safety_stock = safety_factor * demand_std * (lead_time ** 0.5)
        
        optimized_rop = avg_demand + safety_stock
        
        # Calcular EOQ (Economic Order Quantity)
        annual_demand = daily_usage * 365
        ordering_cost = 50  # Costo estimado por orden
        holding_cost_rate = 0.25  # 25% del costo del producto
        unit_cost = product.standard_price or 1
        holding_cost = unit_cost * holding_cost_rate
        
        if annual_demand > 0 and holding_cost > 0:
            optimized_eoq = ((2 * annual_demand * ordering_cost) / holding_cost) ** 0.5
        else:
            optimized_eoq = daily_usage * 30  # Pedido mensual por defecto
        
        # Calcular días de stock
        days_of_stock = current_stock / daily_usage if daily_usage > 0 else 999
        
        # Calcular riesgo de rotura
        if days_of_stock <= 0:
            stockout_risk = 100
        elif days_of_stock < lead_time:
            stockout_risk = min(100, 100 - (days_of_stock / lead_time * 100))
        else:
            stockout_risk = max(0, 20 - days_of_stock)
        
        # Calcular costos
        carrying_cost_total = current_stock * unit_cost * holding_cost_rate / 12  # Mensual
        ordering_cost_total = (annual_demand / max(1, optimized_eoq)) * ordering_cost / 12  # Mensual
        total_cost = carrying_cost_total + ordering_cost_total
        
        # Generar recomendación
        recommendations = []
        if current_stock < optimized_rop:
            recommendations.append(f"⚠️ URGENTE: Stock ({current_stock:.0f}) por debajo del ROP optimizado ({optimized_rop:.0f})")
        if daily_usage > 0 and days_of_stock < lead_time:
            recommendations.append(f"🔴 CRÍTICO: Solo {days_of_stock:.1f} días de stock, lead time es {lead_time} días")
        if current_stock <= 0:
            recommendations.append(f"🚨 SIN STOCK en {warehouse.name}")
        if safety_stock > 0:
            recommendations.append(f"🛡️ Mantener {safety_stock:.0f} unidades de stock de seguridad")
        
        if not recommendations:
            recommendations.append(f"✅ Stock óptimo en {warehouse.name}")
        
        return {
            'current_rop': product.reorder_point or 0,
            'current_eoq': product.eoq or 0,
            'current_safety_stock': product.safety_stock or 0,
            'optimized_rop': optimized_rop,
            'optimized_eoq': optimized_eoq,
            'optimized_safety_stock': safety_stock,
            'stockout_risk': stockout_risk,
            'carrying_cost': carrying_cost_total,
            'ordering_cost': ordering_cost_total,
            'total_cost': total_cost,
            'demand_variability': demand_variability,
            'recommendation': '\n'.join(recommendations),
        }
    
    def action_apply_optimization(self):
        """Aplicar los valores optimizados al producto (a nivel general, no por almacén)"""
        for record in self:
            if record.product_id:
                # Nota: Odoo no tiene ROP por almacén nativamente, 
                # esto actualiza los valores generales del producto
                record.product_id.product_tmpl_id.write({
                    'reorder_point': record.optimized_rop,
                    'eoq': record.optimized_eoq,
                    'safety_stock': record.optimized_safety_stock,
                })
                record.applied = True
        return True
    
    def action_view_warehouse_stock(self):
        """Ver el stock del producto en el almacén"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Stock de {self.product_id.name} en {self.warehouse_id.name}',
            'res_model': 'stock.quant',
            'view_mode': 'tree,form',
            'domain': [
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.warehouse_id.lot_stock_id.id)
            ],
            'context': {'create': False}
        }
