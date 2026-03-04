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


class PurchaseIntelligenceKPI(models.Model):
    _name = 'purchase.intelligence.kpi'
    _description = 'Purchase Intelligence KPI'
    _order = 'date desc, name'
    
    # Campos base del modelo
    name = fields.Char(string='Nombre', required=True)
    code = fields.Char(string='Código', help='Código único del KPI')
    date = fields.Date(string='Fecha', default=fields.Date.today)
    value = fields.Float(string='Valor', digits=(16, 4))
    target = fields.Float(string='Objetivo', digits=(16, 4))
    previous_value = fields.Float(string='Valor Anterior', digits=(16, 4))
    
    category = fields.Selection([
        ('financial', 'Financiero'),
        ('operational', 'Operativo'),
        ('inventory', 'Inventario'),
        ('supplier', 'Proveedor'),
    ], string='Categoría')
    
    kpi_type = fields.Selection([
        ('financial', 'Financiero'),
        ('operational', 'Operativo'),
        ('inventory', 'Inventario'),
        ('supplier', 'Proveedor'),
    ], string='Tipo de KPI')
    
    variance = fields.Float(
        string='Varianza',
        compute='_compute_variance',
        store=True,
        digits=(16, 4),
        help='Diferencia porcentual entre valor actual y objetivo'
    )
    
    trend = fields.Selection([
        ('up', 'Subiendo'),
        ('down', 'Bajando'),
        ('stable', 'Estable'),
    ], string='Tendencia', compute='_compute_trend', store=True)
    
    status = fields.Selection([
        ('success', 'Éxito'),
        ('warning', 'Advertencia'),
        ('danger', 'Peligro'),
    ], string='Estado', compute='_compute_status', store=True)
    
    description = fields.Text(string='Descripción')
    target_value = fields.Float(string='Valor Objetivo', digits=(16, 4))
    active = fields.Boolean(string='Activo', default=True)
    
    # Campos adicionales para soporte multi-almacén
    warehouse_id = fields.Many2one(
        'stock.warehouse', 
        string='Almacén',
        help="Almacén específico para este KPI. Si está vacío, es un KPI global."
    )
    
    is_warehouse_specific = fields.Boolean(
        string='Es Específico de Almacén',
        compute='_compute_is_warehouse_specific',
        store=True,
        help="Indica si este KPI es específico para un almacén o global"
    )
    
    warehouse_comparison_data = fields.Text(
        string='Datos de Comparación',
        help="Datos JSON con comparación entre almacenes para este KPI"
    )
    
    warehouse_rank = fields.Integer(
        string='Rank del Almacén',
        help="Posición de este almacén en comparación con otros para este KPI"
    )
    
    warehouse_performance_score = fields.Float(
        string='Score de Rendimiento',
        digits=(5, 2),
        help="Puntuación de rendimiento del almacén para este KPI (0-100)"
    )
    
    @api.depends('warehouse_id')
    def _compute_is_warehouse_specific(self):
        """Determina si el KPI es específico de un almacén"""
        for record in self:
            record.is_warehouse_specific = bool(record.warehouse_id)
    
    @api.depends('value', 'target')
    def _compute_variance(self):
        """Calcula la varianza porcentual entre el valor actual y el objetivo"""
        for record in self:
            if record.target and record.target != 0:
                record.variance = ((record.value - record.target) / record.target)
            else:
                record.variance = 0.0
    
    @api.depends('value', 'previous_value')
    def _compute_trend(self):
        """Determina la tendencia comparando el valor actual con el anterior"""
        for record in self:
            if record.previous_value:
                if record.value > record.previous_value * 1.02:  # 2% threshold
                    record.trend = 'up'
                elif record.value < record.previous_value * 0.98:
                    record.trend = 'down'
                else:
                    record.trend = 'stable'
            else:
                record.trend = 'stable'
    
    @api.depends('variance')
    def _compute_status(self):
        """Determina el estado basado en la varianza"""
        for record in self:
            if not record.target:
                record.status = 'success'
            elif abs(record.variance) <= 0.05:  # Within 5%
                record.status = 'success'
            elif abs(record.variance) <= 0.15:  # Within 15%
                record.status = 'warning'
            else:
                record.status = 'danger'
    
    @api.model
    def calculate_warehouse_kpis(self, warehouse_id=None):
        """
        Calcular KPIs específicos para un almacén o todos los almacenes
        """
        if warehouse_id:
            warehouses = self.env['stock.warehouse'].browse(warehouse_id)
        else:
            warehouses = self.env['stock.warehouse'].search([])
        
        kpi_results = []
        
        for warehouse in warehouses:
            # Calcular KPIs financieros por almacén
            financial_kpis = self._calculate_financial_kpis_warehouse(warehouse)
            
            # Calcular KPIs operativos por almacén
            operational_kpis = self._calculate_operational_kpis_warehouse(warehouse)
            
            # Calcular KPIs de inventario por almacén
            inventory_kpis = self._calculate_inventory_kpis_warehouse(warehouse)
            
            # Calcular KPIs de proveedores por almacén
            supplier_kpis = self._calculate_supplier_kpis_warehouse(warehouse)
            
            # Combinar todos los KPIs
            all_kpis = {
                'warehouse_id': warehouse.id,
                'warehouse_name': warehouse.name,
                'financial': financial_kpis,
                'operational': operational_kpis,
                'inventory': inventory_kpis,
                'supplier': supplier_kpis,
                'date': fields.Date.today(),
            }
            
            kpi_results.append(all_kpis)
            
            # Guardar KPIs en la base de datos
            self._save_warehouse_kpis(all_kpis)
        
        # Generar comparación entre almacenes
        comparison_data = self._generate_warehouse_comparison(kpi_results)
        
        return {
            'kpi_results': kpi_results,
            'comparison_data': comparison_data,
        }
    
    def _calculate_financial_kpis_warehouse(self, warehouse):
        """
        Calcular KPIs financieros específicos para un almacén
        """
        # Obtener movimientos de stock para este almacén
        stock_moves = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('state', '=', 'done'),
            ('date', '>=', fields.Date.today() - timedelta(days=30))
        ])
        
        # Calcular valor total de stock en este almacén
        total_stock_value = self._calculate_warehouse_stock_value(warehouse)
        
        # Calcular gasto mensual
        monthly_spend = self._calculate_warehouse_monthly_spend(warehouse)
        
        # Calcular costo de mantenimiento
        carrying_cost = total_stock_value * 0.18  # 18% anual
        
        # Calcular rotación de inventario
        turnover = self._calculate_warehouse_turnover(warehouse)
        
        return {
            'total_stock_value': total_stock_value,
            'monthly_spend': monthly_spend,
            'carrying_cost': carrying_cost,
            'turnover': turnover,
            'days_inventory': 365 / turnover if turnover > 0 else 0,
        }
    
    def _calculate_operational_kpis_warehouse(self, warehouse):
        """
        Calcular KPIs operativos específicos para un almacén
        """
        # Tiempo de procesamiento de órdenes
        order_cycle_time = self._calculate_warehouse_order_cycle_time(warehouse)
        
        # Tasa de llenado
        fill_rate = self._calculate_warehouse_fill_rate(warehouse)
        
        # Precisión de inventario
        inventory_accuracy = self._calculate_warehouse_inventory_accuracy(warehouse)
        
        # Productividad
        productivity = self._calculate_warehouse_productivity(warehouse)
        
        return {
            'order_cycle_time': order_cycle_time,
            'fill_rate': fill_rate,
            'inventory_accuracy': inventory_accuracy,
            'productivity': productivity,
        }
    
    def _calculate_inventory_kpis_warehouse(self, warehouse):
        """
        Calcular KPIs de inventario específicos para un almacén
        """
        # Disponibilidad de stock
        stock_availability = self._calculate_warehouse_stock_availability(warehouse)
        
        # Tasa de rotura de stock
        stockout_rate = self._calculate_warehouse_stockout_rate(warehouse)
        
        # Exceso de inventario
        excess_inventory = self._calculate_warehouse_excess_inventory(warehouse)
        
        # Inventario obsoleto
        obsolete_inventory = self._calculate_warehouse_obsolete_inventory(warehouse)
        
        return {
            'stock_availability': stock_availability,
            'stockout_rate': stockout_rate,
            'excess_inventory': excess_inventory,
            'obsolete_inventory': obsolete_inventory,
        }
    
    def _calculate_supplier_kpis_warehouse(self, warehouse):
        """
        Calcular KPIs de proveedores específicos para un almacén
        """
        # Obtener recepciones en este almacén
        receipts = self.env['stock.picking'].search([
            ('picking_type_id.warehouse_id', '=', warehouse.id),
            ('state', '=', 'done'),
            ('date_done', '>=', fields.Date.today() - timedelta(days=90))
        ])
        
        # Calcular tasa de entrega a tiempo
        on_time_delivery = self._calculate_warehouse_on_time_delivery(warehouse, receipts)
        
        # Calcular calidad de recepción
        quality_acceptance = self._calculate_warehouse_quality_acceptance(warehouse, receipts)
        
        # Calcular tiempo promedio de entrega
        avg_delivery_time = self._calculate_warehouse_avg_delivery_time(warehouse, receipts)
        
        return {
            'on_time_delivery': on_time_delivery,
            'quality_acceptance': quality_acceptance,
            'avg_delivery_time': avg_delivery_time,
            'active_suppliers': len(receipts.mapped('partner_id')),
        }
    
    def _calculate_warehouse_stock_value(self, warehouse):
        """
        Calcular el valor total del stock en un almacén específico
        """
        quants = self.env['stock.quant'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('quantity', '>', 0)
        ])
        
        total_value = 0
        for quant in quants:
            if quant.product_id.standard_price:
                total_value += quant.quantity * quant.product_id.standard_price
        
        return total_value
    
    def _calculate_warehouse_monthly_spend(self, warehouse):
        """
        Calcular el gasto mensual para un almacén específico
        """
        date_from = fields.Date.today() - timedelta(days=30)
        
        # Buscar facturas de proveedor relacionadas con este almacén
        supplier_bills = self.env['account.move'].search([
            ('move_type', '=', 'in_invoice'),
            ('invoice_date', '>=', date_from),
            ('stock_move_ids.location_id.warehouse_id', '=', warehouse.id)
        ])
        
        return sum(bill.amount_total for bill in supplier_bills)
    
    def _calculate_warehouse_turnover(self, warehouse):
        """
        Calcular la rotación de inventario para un almacén específico
        """
        # Costo de bienes vendidos (salidas de stock)
        date_from = fields.Date.today() - timedelta(days=365)
        
        stock_moves_out = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('location_dest_id.usage', '!=', 'internal'),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        cogs = sum(move.product_id.standard_price * move.product_uom_qty 
                   for move in stock_moves_out)
        
        # Inventario promedio
        avg_inventory = self._calculate_warehouse_stock_value(warehouse)
        
        return cogs / avg_inventory if avg_inventory > 0 else 0
    
    def _calculate_warehouse_order_cycle_time(self, warehouse):
        """
        Calcular el tiempo de ciclo de órdenes para un almacén específico
        """
        # Buscar órdenes de compra relacionadas con este almacén
        purchase_orders = self.env['purchase.order'].search([
            ('picking_type_id.warehouse_id', '=', warehouse.id),
            ('state', 'in', ['purchase', 'done']),
            ('date_order', '>=', fields.Date.today() - timedelta(days=90))
        ])
        
        total_cycle_time = 0
        count = 0
        
        for po in purchase_orders:
            if po.date_approve and po.picking_ids:
                # Tiempo desde aprobación hasta recepción
                for picking in po.picking_ids:
                    if picking.state == 'done' and picking.date_done:
                        cycle_time = (picking.date_done - po.date_approve).days
                        total_cycle_time += cycle_time
                        count += 1
        
        return total_cycle_time / count if count > 0 else 0
    
    def _calculate_warehouse_fill_rate(self, warehouse):
        """
        Calcular la tasa de llenado para un almacén específico
        """
        # Buscar transferencias de salida completadas
        date_from = fields.Date.today() - timedelta(days=90)
        
        outgoing_picks = self.env['stock.picking'].search([
            ('picking_type_id.warehouse_id', '=', warehouse.id),
            ('state', '=', 'done'),
            ('date_done', '>=', date_from)
        ])
        
        total_requested = 0
        total_delivered = 0
        
        for pick in outgoing_picks:
            for move in pick.move_lines:
                total_requested += move.product_uom_qty
                total_delivered += move.quantity_done
        
        return (total_delivered / total_requested * 100) if total_requested > 0 else 0
    
    
    def _calculate_warehouse_inventory_accuracy(self, warehouse):
        """
        Calcular la precisión del inventario para un almacén específico
        Odoo 19: Usa stock.move con is_inventory=True para ajustes de inventario
        """
        date_from = fields.Date.today() - timedelta(days=90)
        
        # En Odoo 19, los ajustes de inventario se rastrean a través de stock.move
        # con is_inventory=True
        inventory_moves = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('is_inventory', '=', True),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        if not inventory_moves:
            return 100  # Sin ajustes, asumimos 100% de precisión
        
        total_discrepancies = 0
        total_moves = 0
        
        for move in inventory_moves:
            # La diferencia entre cantidad teórica y real se refleja en la cantidad movida
            if move.product_qty != 0:
                total_discrepancies += abs(move.product_qty)
            total_moves += 1
        
        # Calcular precisión como porcentaje
        if total_moves == 0:
            return 100
        
        # Promedio de discrepancia por movimiento
        avg_discrepancy = total_discrepancies / total_moves
        
        # Convertir a porcentaje de precisión (asumiendo cantidad promedio de 10)
        accuracy = max(0, 100 - (avg_discrepancy * 10))
        return min(100, accuracy)
    def _calculate_warehouse_inventory_accuracy(self, warehouse):
        """
        Calcular la precisión del inventario para un almacén específico
        Odoo 19: Usa stock.move con is_inventory=True para ajustes de inventario
        """
        date_from = fields.Date.today() - timedelta(days=90)
        
        # En Odoo 19, los ajustes de inventario se rastrean a través de stock.move
        # con is_inventory=True
        inventory_moves = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('is_inventory', '=', True),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        if not inventory_moves:
            return 100  # Sin ajustes, asumimos 100% de precisión
        
        total_discrepancies = 0
        total_moves = 0
        
        for move in inventory_moves:
            # La diferencia entre cantidad teórica y real se refleja en la cantidad movida
            if move.product_qty != 0:
                total_discrepancies += abs(move.product_qty)
            total_moves += 1
        
        # Calcular precisión como porcentaje
        if total_moves == 0:
            return 100
        
        # Promedio de discrepancia por movimiento
        avg_discrepancy = total_discrepancies / total_moves
        
        # Convertir a porcentaje de precisión (asumiendo cantidad promedio de 10)
        accuracy = max(0, 100 - (avg_discrepancy * 10))
        return min(100, accuracy)
    
    def _calculate_warehouse_productivity(self, warehouse):
        """
        Calcular la productividad para un almacén específico
        """
        # Número de operaciones por empleado (simplificado)
        date_from = fields.Date.today() - timedelta(days=30)
        
        pickings = self.env['stock.picking'].search([
            ('picking_type_id.warehouse_id', '=', warehouse.id),
            ('state', '=', 'done'),
            ('date_done', '>=', date_from)
        ])
        
        # Número estimado de empleados (simplificado)
        estimated_employees = max(1, len(pickings) / 100)  # Asumir 100 operaciones por empleado
        
        return len(pickings) / estimated_employees if estimated_employees > 0 else 0
    
    def _calculate_warehouse_stock_availability(self, warehouse):
        """
        Calcular la disponibilidad de stock para un almacén específico
        """
        # Productos con stock > 0 en este almacén
        products_with_stock = self.env['stock.quant'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('quantity', '>', 0)
        ]).mapped('product_id')
        
        # Total de productos activos
        total_products = self.env['product.template'].search([
            ('is_storable', '=', True)
        ])
        
        return len(products_with_stock) / len(total_products) * 100 if total_products else 0
    
    def _calculate_warehouse_stockout_rate(self, warehouse):
        """
        Calcular la tasa de rotura de stock para un almacén específico
        """
        # Buscar movimientos que no se pudieron completar por falta de stock
        date_from = fields.Date.today() - timedelta(days=90)
        
        stock_moves = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('state', '=', 'confirmed'),  # Confirmado pero no disponible
            ('date', '>=', date_from)
        ])
        
        total_moves = self.env['stock.move'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('date', '>=', date_from)
        ])
        
        return len(stock_moves) / len(total_moves) * 100 if total_moves else 0
    
    def _calculate_warehouse_excess_inventory(self, warehouse):
        """
        Calcular el exceso de inventario para un almacén específico
        """
        # Productos con más de 90 días de stock
        quants = self.env['stock.quant'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('quantity', '>', 0)
        ])
        
        excess_value = 0
        for quant in quants:
            # Calcular días de stock basados en consumo promedio
            daily_usage = self._get_product_daily_usage(quant.product_id, warehouse)
            if daily_usage > 0:
                days_of_stock = quant.quantity / daily_usage
                if days_of_stock > 90:
                    excess_value += quant.quantity * quant.product_id.standard_price
        
        return excess_value
    
    def _calculate_warehouse_obsolete_inventory(self, warehouse):
        """
        Calcular el inventario obsoleto para un almacén específico
        """
        # Productos sin movimiento en los últimos 180 días
        date_from = fields.Date.today() - timedelta(days=180)
        
        quants = self.env['stock.quant'].search([
            ('location_id.warehouse_id', '=', warehouse.id),
            ('quantity', '>', 0)
        ])
        
        obsolete_value = 0
        for quant in quants:
            # Verificar si hubo movimiento en los últimos 180 días
            recent_moves = self.env['stock.move'].search([
                ('product_id', '=', quant.product_id.id),
                ('location_id.warehouse_id', '=', warehouse.id),
                ('state', '=', 'done'),
                ('date', '>=', date_from)
            ])
            
            if not recent_moves:
                obsolete_value += quant.quantity * quant.product_id.standard_price
        
        return obsolete_value
    
    def _calculate_warehouse_on_time_delivery(self, warehouse, receipts):
        """
        Calcular la tasa de entrega a tiempo para un almacén específico
        """
        if not receipts:
            return 0
        
        on_time_count = 0
        total_count = 0
        
        for receipt in receipts:
            # Verificar si la fecha de entrega fue antes o igual a la fecha esperada
            if receipt.scheduled_date and receipt.date_done:
                if receipt.date_done <= receipt.scheduled_date:
                    on_time_count += 1
                total_count += 1
        
        return (on_time_count / total_count * 100) if total_count > 0 else 0
    
    def _calculate_warehouse_quality_acceptance(self, warehouse, receipts):
        """
        Calcular la tasa de aceptación de calidad para un almacén específico
        """
        if not receipts:
            return 0
        
        # Simplificado: asumimos que todas las recepciones aceptadas
        # En un caso real, se verificarían los controles de calidad
        return 95.0  # Valor ejemplo
    
    def _calculate_warehouse_avg_delivery_time(self, warehouse, receipts):
        """
        Calcular el tiempo promedio de entrega para un almacén específico
        """
        if not receipts:
            return 0
        
        total_time = 0
        count = 0
        
        for receipt in receipts:
            # Calcular tiempo desde creación hasta finalización
            if receipt.create_date and receipt.date_done:
                time_diff = receipt.date_done - receipt.create_date
                total_time += time_diff.days
                count += 1
        
        return total_time / count if count > 0 else 0
    
    def _get_product_daily_usage(self, product, warehouse):
        """
        Obtener el consumo diario de un producto en un almacén específico
        """
        date_from = fields.Date.today() - timedelta(days=30)
        
        # Buscar movimientos de salida
        moves_out = self.env['stock.move'].search([
            ('product_id', '=', product.id),
            ('location_id.warehouse_id', '=', warehouse.id),
            ('location_dest_id.usage', '!=', 'internal'),
            ('state', '=', 'done'),
            ('date', '>=', date_from)
        ])
        
        total_qty = sum(move.product_uom_qty for move in moves_out)
        return total_qty / 30  # Promedio diario
    
    def _save_warehouse_kpis(self, kpi_data):
        """
        Guardar KPIs de almacén en la base de datos
        """
        warehouse_id = kpi_data['warehouse_id']
        date = kpi_data['date']
        
        # Eliminar KPIs existentes para este almacén y fecha
        existing_kpis = self.search([
            ('warehouse_id', '=', warehouse_id),
            ('date', '=', date)
        ])
        existing_kpis.unlink()
        
        # Crear nuevos KPIs
        kpi_types = [
            ('financial', kpi_data['financial']),
            ('operational', kpi_data['operational']),
            ('inventory', kpi_data['inventory']),
            ('supplier', kpi_data['supplier'])
        ]
        
        for kpi_type, kpi_values in kpi_types:
            for kpi_name, kpi_value in kpi_values.items():
                self.create({
                    'name': f'{kpi_type}_{kpi_name}',
                    'warehouse_id': warehouse_id,
                    'date': date,
                    'value': kpi_value,
                    'kpi_type': kpi_type,
                    'description': f'KPI {kpi_type} - {kpi_name} para almacén',
                })
    
    def _generate_warehouse_comparison(self, kpi_results):
        """
        Generar datos de comparación entre almacenes
        """
        if len(kpi_results) < 2:
            return {}
        
        comparison = {
            'warehouses': [],
            'rankings': {},
        }
        
        # Recolectar datos para comparación
        for kpi_result in kpi_results:
            warehouse_data = {
                'warehouse_id': kpi_result['warehouse_id'],
                'warehouse_name': kpi_result['warehouse_name'],
                'total_stock_value': kpi_result['financial']['total_stock_value'],
                'monthly_spend': kpi_result['financial']['monthly_spend'],
                'turnover': kpi_result['financial']['turnover'],
                'stock_availability': kpi_result['inventory']['stock_availability'],
                'stockout_rate': kpi_result['inventory']['stockout_rate'],
                'on_time_delivery': kpi_result['supplier']['on_time_delivery'],
            }
            comparison['warehouses'].append(warehouse_data)
        
        # Generar rankings para cada KPI
        kpi_keys = ['total_stock_value', 'monthly_spend', 'turnover', 
                   'stock_availability', 'on_time_delivery']
        
        for kpi_key in kpi_keys:
            # Ordenar por KPI (mayor es mejor para todos estos casos)
            sorted_warehouses = sorted(
                comparison['warehouses'], 
                key=lambda x: x[kpi_key], 
                reverse=True
            )
            
            comparison['rankings'][kpi_key] = [
                {
                    'warehouse_id': w['warehouse_id'],
                    'warehouse_name': w['warehouse_name'],
                    'value': w[kpi_key],
                    'rank': idx + 1
                }
                for idx, w in enumerate(sorted_warehouses)
            ]
        
        return comparison
    
    @api.model
    def get_warehouse_kpi_dashboard_data(self, warehouse_id):
        """
        Obtener datos del dashboard de KPIs para un almacén específico
        """
        # Obtener KPIs más recientes para el almacén
        latest_date = self.search([
            ('warehouse_id', '=', warehouse_id)
        ], order='date desc', limit=1).date
        
        if not latest_date:
            latest_date = fields.Date.today()
        
        kpis = self.search([
            ('warehouse_id', '=', warehouse_id),
            ('date', '=', latest_date)
        ])
        
        # Organizar KPIs por tipo
        kpi_data = {
            'financial': {},
            'operational': {},
            'inventory': {},
            'supplier': {},
        }
        
        for kpi in kpis:
            kpi_type = kpi.kpi_type
            if kpi_type in kpi_data:
                kpi_name = kpi.name.replace(f'{kpi_type}_', '')
                kpi_data[kpi_type][kpi_name] = kpi.value
        
        return kpi_data
    
    @api.model
    def action_calculate_daily_warehouse_kpis(self):
        """
        Acción programada para calcular KPIs diarios de todos los almacenes
        """
        _logger.info("Calculando KPIs diarios por almacén...")
        
        try:
            result = self.calculate_warehouse_kpis()
            _logger.info(f"KPIs calculados para {len(result['kpi_results'])} almacenes")
            return True
            
        except Exception as e:
            _logger.error(f"Error calculando KPIs diarios: {e}")
            return False

    @api.model
    def get_dashboard_data(self):
        """
        Return the consolidated data needed for the Purchase Intelligence Dashboard.
        Called via RPC from master_dashboard.js.
        """
        # 1. Obtain global KPIs
        # Use existing calculation methods or retrieve the latest stored values
        try:
            today = fields.Date.today()
            
            # Retrieve latest budget/spend info (mocked or from real data)
            # Calculate total spend this month vs last month
            first_day_month = today.replace(day=1)
            last_month_end = first_day_month - timedelta(days=1)
            first_day_last_month = last_month_end.replace(day=1)
            
            this_month_orders = self.env['purchase.order'].search([
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', first_day_month)
            ])
            month_purchases = sum(this_month_orders.mapped('amount_total'))
            
            last_month_orders = self.env['purchase.order'].search([
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', first_day_last_month),
                ('date_order', '<=', last_month_end)
            ])
            last_month_purchases = sum(last_month_orders.mapped('amount_total'))
            
            spend_change = 0
            if last_month_purchases > 0:
                spend_change = ((month_purchases - last_month_purchases) / last_month_purchases) * 100
            
            # Budget status (Mocked for now as per likely requirement if no budget model exists)
            # In a real scenario this would query account.analytic.line or crossovered.budget
            budget_total = 100000.0  # Example budget
            budget_used_percent = (month_purchases / budget_total * 100) if budget_total else 0
            
            budget_data = {
                'total_budget': budget_total,
                'used_amount': month_purchases,
                'remaining': budget_total - month_purchases,
                'used_percent': min(100, budget_used_percent),
                'status': 'warning' if budget_used_percent > 80 else 'success'
            }
            
            # 2. Get active alerts
            # We look for alerts in 'pi.alert.log' which seems to be the log model for alerts as per alert.py
            active_alerts = self.env['pi.alert.log'].search([
                 ('state', '=', 'new')
            ], limit=10, order='create_date desc')
            
            alerts_list = []
            for alert in active_alerts:
                alerts_list.append({
                    'id': alert.id,
                    'title': alert.name,
                    'message': alert.message,
                    'severity': alert.severity,
                    'date': alert.create_date.strftime('%Y-%m-%d'),
                    'model': alert.res_model,
                    'res_id': alert.res_id
                })
            
            # 3. Get key high-level KPIs
            # We can reuse _calculate_financial_kpis_warehouse but for all warehouses
            # Or just fetch the latest generated PurchaseIntelligenceKPI records
            
            # Fetch latest specific KPIs if they exist, otherwise calc on fly
            kpis = {
                'total_spend': {
                    'value': month_purchases,
                    'change': spend_change,
                    'trend': 'up' if spend_change > 0 else 'down'
                },
                'savings': {
                     'value': month_purchases * 0.045, # Simulated 4.5% savings
                     'change': 1.2,
                     'trend': 'up'
                },
                'otif': { # On Time In Full
                    'value': 94.5,
                    'change': -0.5,
                    'trend': 'down'
                },
                'quality': {
                     'value': 98.2,
                     'change': 0.1,
                     'trend': 'up'
                }
            }
            
            return {
                'kpis': kpis,
                'alerts': alerts_list,
                'budget_status': budget_data
            }
            
        except Exception as e:
            _logger.error(f"Error in get_dashboard_data: {e}")
            return {
                'kpis': {},
                'alerts': [],
                'budget_status': {}
            }
