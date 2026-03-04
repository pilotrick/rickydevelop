# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class WarehouseIntelligence(models.Model):
    _name = 'warehouse.intelligence'
    _description = 'Inteligencia de Compras por Almacén'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'warehouse_id, date desc'

    name = fields.Char(string='Nombre', required=True, compute='_compute_name', store=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Almacén', required=True, ondelete='cascade')
    date = fields.Date(string='Fecha', default=fields.Date.context_today, required=True)
    
    # === MÉTRICAS PRINCIPALES ===
    total_products = fields.Integer(string='Total Productos', compute='_compute_metrics', store=True)
    products_need_reorder = fields.Integer(string='Productos con Reorden', compute='_compute_metrics', store=True)
    critical_products = fields.Integer(string='Productos Críticos', compute='_compute_metrics', store=True)
    low_stock_products = fields.Integer(string='Productos con Stock Bajo', compute='_compute_metrics', store=True)
    
    # === VALORES MONETARIOS ===
    total_stock_value = fields.Float(string='Valor Total Stock', compute='_compute_metrics', store=True)
    pending_order_value = fields.Float(string='Valor Órdenes Pendientes', compute='_compute_metrics', store=True)
    monthly_spend = fields.Float(string='Gasto Mensual', compute='_compute_metrics', store=True)
    
    # === KPIs ESPECÍFICOS POR ALMACÉN ===
    stock_turnover = fields.Float(string='Rotación Inventario', compute='_compute_kpis', store=True)
    days_of_inventory = fields.Float(string='Días de Inventario', compute='_compute_kpis', store=True)
    stock_availability = fields.Float(string='Disponibilidad de Stock (%)', compute='_compute_kpis', store=True)
    stockout_rate = fields.Float(string='Tasa de Rotura (%)', compute='_compute_kpis', store=True)
    
    # === ANÁLISIS ABC POR ALMACÉN ===
    abc_a_count = fields.Integer(string='Productos Clase A', compute='_compute_abc_analysis', store=True)
    abc_a_value = fields.Float(string='Valor Clase A', compute='_compute_abc_analysis', store=True)
    abc_b_count = fields.Integer(string='Productos Clase B', compute='_compute_abc_analysis', store=True)
    abc_b_value = fields.Float(string='Valor Clase B', compute='_compute_abc_analysis', store=True)
    abc_c_count = fields.Integer(string='Productos Clase C', compute='_compute_abc_analysis', store=True)
    abc_c_value = fields.Float(string='Valor Clase C', compute='_compute_abc_analysis', store=True)
    
    # === RENDIMIENTO DE PROVEEDORES POR ALMACÉN ===
    active_suppliers = fields.Integer(string='Proveedores Activos', compute='_compute_supplier_metrics', store=True)
    avg_delivery_time = fields.Float(string='Tiempo Promedio Entrega', compute='_compute_supplier_metrics', store=True)
    on_time_delivery_rate = fields.Float(string='Tasa Entrega a Tiempo (%)', compute='_compute_supplier_metrics', store=True)
    
    # === COMPARACIÓN CON OTROS ALMACENES ===
    performance_rank = fields.Integer(string='Rank de Rendimiento', compute='_compute_comparison', store=True)
    efficiency_score = fields.Float(string='Puntuación Eficiencia', compute='_compute_comparison', store=True)
    
    # === ALERTAS ESPECÍFICAS ===
    alert_count = fields.Integer(string='Cantidad de Alertas', compute='_compute_alerts', store=True)
    critical_alerts = fields.Text(string='Alertas Críticas', compute='_compute_alerts', store=True)
    
    @api.depends('warehouse_id')
    def _compute_name(self):
        for record in self:
            record.name = f"Inteligencia {record.warehouse_id.name or 'Sin Nombre'}"

    @api.depends('warehouse_id', 'date')
    def _compute_metrics(self):
        """
        Calcular métricas específicas para este almacén
        """
        today = fields.Date.context_today(self)
        one_month_ago = today - timedelta(days=30)
        
        for record in self:
            # Productos en este almacén
            domain = [
                ('is_storable', '=', True),
                ('qty_available', '>', 0)
            ]
            
            # Si hay un almacén específico, filtrar por stock en ese almacén
            if record.warehouse_id:
                domain.append(('location_ids.warehouse_id', '=', record.warehouse_id.id))
            
            products = self.env['product.product'].search(domain)
            
            # Productos que necesitan reorden en este almacén
            reorder_domain = [
                ('is_storable', '=', True),
                ('needs_reorder', '=', True)
            ]
            if record.warehouse_id:
                # Para productos que necesitan reorden, verificamos stock en este almacén específico
                products_need_reorder = self.env['product.product'].search(reorder_domain)
                warehouse_products_need_reorder = []
                
                for product in products_need_reorder:
                    # Verificar stock específico en este almacén
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if stock_quant and stock_quant.quantity <= product.reorder_point_suggested:
                        warehouse_products_need_reorder.append(product)
                
                record.products_need_reorder = len(warehouse_products_need_reorder)
            else:
                record.products_need_reorder = 0
            
            # Productos críticos en este almacén
            critical_domain = [
                ('is_storable', '=', True),
                ('stockout_risk', 'in', ['critical', 'high'])
            ]
            if record.warehouse_id:
                critical_products = self.env['product.product'].search(critical_domain)
                warehouse_critical_products = []
                
                for product in critical_products:
                    # Verificar si realmente es crítico en este almacén
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if stock_quant and stock_quant.quantity <= product.safety_stock:
                        warehouse_critical_products.append(product)
                
                record.critical_products = len(warehouse_critical_products)
            else:
                record.critical_products = 0
            
            # Productos con stock bajo en este almacén
            low_stock_domain = [
                ('is_storable', '=', True),
                ('days_of_stock', '<', 7),
                ('days_of_stock', '>', 0)
            ]
            if record.warehouse_id:
                low_stock_products = self.env['product.product'].search(low_stock_domain)
                warehouse_low_stock_products = []
                
                for product in low_stock_products:
                    # Verificar stock específico en este almacén
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if stock_quant and stock_quant.quantity < 10:  # Menos de 10 unidades
                        warehouse_low_stock_products.append(product)
                
                record.low_stock_products = len(warehouse_low_stock_products)
            else:
                record.low_stock_products = 0
            
            # Calcular valores monetarios específicos del almacén
            record.total_products = len(products)
            
            # Valor total del stock en este almacén
            total_value = 0
            if record.warehouse_id:
                for product in products:
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    if stock_quant:
                        total_value += stock_quant.quantity * (product.standard_price or 0)
            
            record.total_stock_value = total_value
            
            # Valor de órdenes pendientes para este almacén
            pending_order_domain = [
                ('state', 'in', ['purchase', 'done']),
                ('date_order', '>=', one_month_ago)
            ]
            if record.warehouse_id:
                # Filtrar por picking destinado a este almacén
                pending_order_domain.append(('picking_ids.location_dest_id.warehouse_id', '=', record.warehouse_id.id))
            
            pending_orders = self.env['purchase.order'].search(pending_order_domain)
            record.pending_order_value = sum(pending_orders.mapped('amount_total'))
            
            # Gasto mensual para este almacén
            record.monthly_spend = record.pending_order_value

    @api.depends('warehouse_id', 'date', 'total_stock_value')
    def _compute_kpis(self):
        """
        Calcular KPIs específicos para este almacén
        """
        for record in self:
            # Rotación de inventario específica del almacén
            if record.total_stock_value > 0:
                # Calcular COGS específico del almacén
                one_month_ago = record.date - timedelta(days=30)
                cogs = 0
                
                if record.warehouse_id:
                    # Buscar movimientos de salida de este almacén
                    moves = self.env['stock.move'].search([
                        ('date', '>=', one_month_ago),
                        ('picking_type_id.code', '=', 'outgoing'),
                        ('state', '=', 'done'),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id)
                    ])
                    
                    for move in moves:
                        cogs += move.product_uom_qty * move.product_id.standard_price
                
                # Anualizar para cálculo de rotación
                annualized_cogs = cogs * 12
                record.stock_turnover = annualized_cogs / record.total_stock_value
                record.days_of_inventory = 365 / record.stock_turnover if record.stock_turnover > 0 else 0
            else:
                record.stock_turnover = 0
                record.days_of_inventory = 0
            
            # Disponibilidad de stock específica del almacén
            if record.total_products > 0:
                in_stock_count = record.total_products - record.critical_products - record.low_stock_products
                record.stock_availability = (in_stock_count / record.total_products * 100) if record.total_products > 0 else 0
                record.stockout_rate = (record.critical_products / record.total_products * 100) if record.total_products > 0 else 0
            else:
                record.stock_availability = 0
                record.stockout_rate = 0

    @api.depends('warehouse_id', 'date')
    def _compute_abc_analysis(self):
        """
        Análisis ABC específico para este almacén
        """
        for record in self:
            # Obtener productos con valor en este almacén
            products_with_value = []
            
            if record.warehouse_id:
                all_products = self.env['product.product'].search([('is_storable', '=', True)])
                
                for product in all_products:
                    # Obtener stock y valor específico de este almacén
                    stock_quant = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id.warehouse_id', '=', record.warehouse_id.id),
                        ('quantity', '>', 0)
                    ], limit=1)
                    
                    if stock_quant:
                        product_value = stock_quant.quantity * (product.standard_price or 0)
                        if product_value > 0:
                            products_with_value.append({
                                'product': product,
                                'value': product_value
                            })
            
            # Ordenar por valor (mayor a menor)
            products_with_value.sort(key=lambda x: x['value'], reverse=True)
            
            # Calcular clasificación ABC
            total_value = sum(p['value'] for p in products_with_value)
            cum_value = 0
            
            a_count = b_count = c_count = 0
            a_value = b_value = c_value = 0
            
            for product_data in products_with_value:
                cum_value += product_data['value']
                percent = (cum_value / total_value * 100) if total_value > 0 else 0
                
                if percent <= 80:  # 80% del valor = Clase A
                    a_count += 1
                    a_value += product_data['value']
                elif percent <= 95:  # 95% del valor = Clase B
                    b_count += 1
                    b_value += product_data['value']
                else:  # Resto = Clase C
                    c_count += 1
                    c_value += product_data['value']
            
            record.abc_a_count = a_count
            record.abc_a_value = a_value
            record.abc_b_count = b_count
            record.abc_b_value = b_value
            record.abc_c_count = c_count
            record.abc_c_value = c_value

    @api.depends('warehouse_id', 'date')
    def _compute_supplier_metrics(self):
        """
        Métricas de proveedores específicas para este almacén
        """
        for record in self:
            if not record.warehouse_id:
                record.active_suppliers = 0
                record.avg_delivery_time = 0
                record.on_time_delivery_rate = 0
                continue
            
            # Proveedores con entregas a este almacén
            one_month_ago = record.date - timedelta(days=30)
            
            # Buscar recepciones en este almacén
            pickings = self.env['stock.picking'].search([
                ('picking_type_id.code', '=', 'incoming'),
                ('state', '=', 'done'),
                ('date_done', '>=', one_month_ago),
                ('location_dest_id.warehouse_id', '=', record.warehouse_id.id)
            ])
            
            # Obtener proveedores únicos
            supplier_ids = set()
            total_delivery_time = 0
            delivery_count = 0
            on_time_count = 0
            
            for picking in pickings:
                if picking.partner_id:
                    supplier_ids.add(picking.partner_id.id)
                
                # Calcular tiempo de entrega
                if picking.date_done and picking.scheduled_date:
                    delivery_time = (picking.date_done.date() - picking.scheduled_date.date()).days
                    total_delivery_time += delivery_time
                    delivery_count += 1
                    
                    # Entrega a tiempo (dentro de la fecha programada + 1 día)
                    if delivery_time <= 1:
                        on_time_count += 1
            
            record.active_suppliers = len(supplier_ids)
            record.avg_delivery_time = total_delivery_time / delivery_count if delivery_count > 0 else 0
            record.on_time_delivery_rate = (on_time_count / delivery_count * 100) if delivery_count > 0 else 0

    @api.depends('warehouse_id', 'stock_turnover', 'stock_availability', 'on_time_delivery_rate')
    def _compute_comparison(self):
        """
        Comparación de rendimiento con otros almacenes
        """
        for record in self:
            # Obtener todos los almacenes
            all_warehouses = self.search([('date', '=', record.date)])
            
            if len(all_warehouses) <= 1:
                record.performance_rank = 1
                record.efficiency_score = 100.0
                continue
            
            # Calcular puntuación de eficiencia (0-100)
            efficiency_factors = {
                'stock_turnover': {'weight': 0.3, 'higher_better': True},
                'stock_availability': {'weight': 0.3, 'higher_better': True},
                'on_time_delivery_rate': {'weight': 0.2, 'higher_better': True},
                'active_suppliers': {'weight': 0.1, 'higher_better': True},  # Más proveedores = mejor
                'critical_products': {'weight': 0.1, 'higher_better': False},  # Menos críticos = mejor
            }
            
            score = 0
            for factor_name, factor_config in efficiency_factors.items():
                factor_value = getattr(record, factor_name, 0)
                
                # Normalizar valor (0-100)
                if factor_name == 'stock_turnover':
                    # Rotación: normalizar comparando con el máximo
                    max_turnover = max(getattr(wh, factor_name, 0) for wh in all_warehouses)
                    normalized_value = (factor_value / max_turnover * 100) if max_turnover > 0 else 0
                elif factor_name == 'critical_products':
                    # Productos críticos: invertir (menos es mejor)
                    max_critical = max(getattr(wh, factor_name, 0) for wh in all_warehouses)
                    normalized_value = (1 - (factor_value / max_critical)) * 100 if max_critical > 0 else 100
                else:
                    # Otros factores: normalizar comparando con el máximo
                    max_value = max(getattr(wh, factor_name, 0) for wh in all_warehouses)
                    normalized_value = (factor_value / max_value * 100) if max_value > 0 else 0
                
                # Aplicar peso
                if factor_config['higher_better']:
                    score += normalized_value * factor_config['weight']
                else:
                    score += (100 - normalized_value) * factor_config['weight']
            
            record.efficiency_score = min(100, max(0, score))
            
            # Calcular rank (1 = mejor)
            sorted_warehouses = sorted(all_warehouses, key=lambda x: x.efficiency_score, reverse=True)
            for i, warehouse in enumerate(sorted_warehouses, 1):
                if warehouse.id == record.id:
                    record.performance_rank = i
                    break

    @api.depends('warehouse_id', 'critical_products', 'low_stock_products', 'products_need_reorder')
    def _compute_alerts(self):
        """
        Generar alertas específicas para este almacén
        """
        for record in self:
            alerts = []
            
            # Alerta de productos críticos
            if record.critical_products > 0:
                alerts.append(f"🔴 {record.critical_products} productos en riesgo CRÍTICO de rotura de stock")
            
            # Alerta de stock bajo
            if record.low_stock_products > 5:
                alerts.append(f"🟠 {record.low_stock_products} productos con stock bajo (< 7 días)")
            
            # Alerta de muchos productos necesitando reorden
            if record.products_need_reorder > 10:
                alerts.append(f"🟡 {record.products_need_reorder} productos necesitan reorden")
            
            # Alerta de disponibilidad baja
            if record.stock_availability < 90:
                alerts.append(f"🟡 Disponibilidad de stock baja: {record.stock_availability:.1f}%")
            
            record.alert_count = len(alerts)
            record.critical_alerts = " | ".join(alerts) if alerts else "Sin alertas críticas"

    @api.model
    def action_generate_warehouse_intelligence(self):
        """
        Método Cron: Generar inteligencia para todos los almacenes
        Se ejecuta automáticamente cada día.
        """
        _logger.info("=== Generando inteligencia por almacén ===")
        
        warehouses = self.env['stock.warehouse'].search([])
        today = fields.Date.context_today(self)
        
        created_count = 0
        updated_count = 0
        
        for warehouse in warehouses:
            # Verificar si ya existe registro para hoy
            existing = self.search([
                ('warehouse_id', '=', warehouse.id),
                ('date', '=', today)
            ], limit=1)
            
            vals = {
                'warehouse_id': warehouse.id,
                'date': today,
            }
            
            if existing:
                existing.write(vals)
                updated_count += 1
            else:
                self.create(vals)
                created_count += 1
        
        _logger.info(f"Inteligencia de almacén generada: {created_count} nuevos, {updated_count} actualizados")
        return {'created': created_count, 'updated': updated_count}

    @api.model
    def get_warehouse_comparison_data(self):
        """
        Obtener datos comparativos entre almacenes
        """
        today = fields.Date.context_today(self)
        warehouse_data = self.search([('date', '=', today)])
        
        comparison_data = []
        for data in warehouse_data:
            comparison_data.append({
                'warehouse_id': data.warehouse_id.id,
                'warehouse_name': data.warehouse_id.name,
                'efficiency_score': data.efficiency_score,
                'performance_rank': data.performance_rank,
                'total_products': data.total_products,
                'critical_products': data.critical_products,
                'stock_availability': data.stock_availability,
                'stock_turnover': data.stock_turnover,
                'monthly_spend': data.monthly_spend,
                'active_suppliers': data.active_suppliers,
                'on_time_delivery_rate': data.on_time_delivery_rate,
            })
        
        # Ordenar por efficiency_score descendente
        comparison_data.sort(key=lambda x: x['efficiency_score'], reverse=True)
        
        return {
            'comparison_data': comparison_data,
            'best_warehouse': comparison_data[0] if comparison_data else None,
            'worst_warehouse': comparison_data[-1] if comparison_data else None,
        }

    @api.model
    def get_warehouse_dashboard_data(self, warehouse_id=None):
        """
        Obtener datos específicos para dashboard de un almacén
        """
        if not warehouse_id:
            return {}
        
        today = fields.Date.context_today(self)
        warehouse_intel = self.search([
            ('warehouse_id', '=', warehouse_id),
            ('date', '=', today)
        ], limit=1)
        
        if not warehouse_intel:
            return {}
        
        # Productos que necesitan acción inmediata en este almacén
        critical_products_data = []
        if warehouse_intel.warehouse_id:
            critical_domain = [
                ('is_storable', '=', True),
                ('stockout_risk', 'in', ['critical', 'high'])
            ]
            
            products = self.env['product.product'].search(critical_domain)
            for product in products[:10]:  # Top 10 críticos
                # Verificar stock específico en este almacén
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id.warehouse_id', '=', warehouse_intel.warehouse_id.id),
                    ('quantity', '>', 0)
                ], limit=1)
                
                critical_products_data.append({
                    'id': product.id,
                    'name': product.name,
                    'current_stock': stock_quant.quantity if stock_quant else 0,
                    'reorder_point': product.reorder_point_suggested,
                    'safety_stock': product.safety_stock,
                    'days_of_stock': product.days_of_stock,
                    'daily_usage': product.daily_usage,
                })
        
        # Sugerencias de reorden específicas del almacén
        reorder_suggestions = []
        if warehouse_intel.warehouse_id:
            reorder_domain = [
                ('is_storable', '=', True),
                ('needs_reorder', '=', True)
            ]
            
            products = self.env['product.product'].search(reorder_domain)
            for product in products[:10]:  # Top 10 sugerencias
                # Verificar stock específico en este almacén
                stock_quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id.warehouse_id', '=', warehouse_intel.warehouse_id.id),
                    ('quantity', '>', 0)
                ], limit=1)
                
                if stock_quant and stock_quant.quantity <= product.reorder_point_suggested:
                    reorder_suggestions.append({
                        'id': product.id,
                        'name': product.name,
                        'current_stock': stock_quant.quantity,
                        'suggested_qty': product.suggested_order_qty,
                        'urgency': product.stockout_risk,
                        'supplier_name': product.seller_ids[0].partner_id.name if product.seller_ids else 'Sin proveedor',
                    })
        
        return {
            'warehouse_info': {
                'id': warehouse_intel.warehouse_id.id,
                'name': warehouse_intel.warehouse_id.name,
                'efficiency_score': warehouse_intel.efficiency_score,
                'performance_rank': warehouse_intel.performance_rank,
            },
            'metrics': {
                'total_products': warehouse_intel.total_products,
                'products_need_reorder': warehouse_intel.products_need_reorder,
                'critical_products': warehouse_intel.critical_products,
                'low_stock_products': warehouse_intel.low_stock_products,
                'total_stock_value': warehouse_intel.total_stock_value,
                'pending_order_value': warehouse_intel.pending_order_value,
                'monthly_spend': warehouse_intel.monthly_spend,
                'stock_turnover': warehouse_intel.stock_turnover,
                'days_of_inventory': warehouse_intel.days_of_inventory,
                'stock_availability': warehouse_intel.stock_availability,
                'stockout_rate': warehouse_intel.stockout_rate,
            },
            'abc_analysis': {
                'a_count': warehouse_intel.abc_a_count,
                'a_value': warehouse_intel.abc_a_value,
                'b_count': warehouse_intel.abc_b_count,
                'b_value': warehouse_intel.abc_b_value,
                'c_count': warehouse_intel.abc_c_count,
                'c_value': warehouse_intel.abc_c_value,
            },
            'supplier_metrics': {
                'active_suppliers': warehouse_intel.active_suppliers,
                'avg_delivery_time': warehouse_intel.avg_delivery_time,
                'on_time_delivery_rate': warehouse_intel.on_time_delivery_rate,
            },
            'critical_products': critical_products_data,
            'reorder_suggestions': reorder_suggestions,
            'alerts': {
                'alert_count': warehouse_intel.alert_count,
                'critical_alerts': warehouse_intel.critical_alerts,
            },
        }