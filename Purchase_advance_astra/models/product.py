# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import math
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Helper field for storable products
    is_storable = fields.Boolean(
        string='Is Storable',
        compute='_compute_is_storable',
        store=True,
        help='True if product type is storable (product)'
    )

    # Clasificación ABC-XYZ
    abc_classification = fields.Selection([
        ('A', 'A - Valor Alto'),
        ('B', 'B - Valor Medio'),
        ('C', 'C - Valor Bajo')
    ], string='Clasificación ABC', compute='_compute_abc_classification', store=True)

    xyz_classification = fields.Selection([
        ('X', 'X - Demanda Estable'),
        ('Y', 'Y - Demanda Variable'),
        ('Z', 'Z - Demanda Esporádica')
    ], string='Clasificación XYZ')

    # Análisis FSN (Fast, Slow, Non-moving)
    fsn_classification = fields.Selection([
        ('F', 'Rápido (Fast)'),
        ('S', 'Lento (Slow)'),
        ('N', 'Sin Movimiento (Non-moving)'),
        ('D', 'Muerto (Dead)')
    ], string='Análisis FSN', compute='_compute_fsn_classification', store=True)

    # Análisis VED (Vital, Essential, Desirable)
    ved_classification = fields.Selection([
        ('V', 'Vital'),
        ('E', 'Esencial'),
        ('D', 'Deseable')
    ], string='Análisis VED', default='D')

    # === CAMPOS CALCULADOS AUTOMÁTICAMENTE ===
    daily_usage = fields.Float(
        string='Consumo Diario Promedio',
        compute='_compute_consumption_stats',
        store=True,
        help='Calculado automáticamente de los últimos 90 días de movimientos de stock'
    )
    weekly_usage = fields.Float(
        string='Consumo Semanal',
        compute='_compute_consumption_stats',
        store=True
    )
    monthly_usage = fields.Float(
        string='Consumo Mensual',
        compute='_compute_consumption_stats',
        store=True
    )
    
    lead_time_days = fields.Integer(
        string='Tiempo de Entrega (Días)',
        compute='_compute_lead_time_days',
        store=True
    )
    
    # === STOCK INTELIGENTE ===
    safety_stock = fields.Float(
        string='Stock de Seguridad',
        compute='_compute_intelligent_stock_levels',
        store=True,
        help='Calculado para cubrir variaciones en demanda y entregas'
    )
    reorder_point = fields.Float(
        string='Punto de Reorden',
        compute='_compute_intelligent_stock_levels',
        store=True,
        help='Cuando el stock llegue a este nivel, debe pedir'
    )
    max_stock = fields.Float(
        string='Stock Máximo',
        compute='_compute_intelligent_stock_levels',
        store=True
    )
    eoq = fields.Float(
        string='Cantidad Óptima de Pedido',
        compute='_compute_intelligent_stock_levels',
        store=True
    )
    
    # === INDICADORES DE RIESGO ===
    # === STOCK ESPECÍFICO POR ALMACÉN ===
    warehouse_intelligence_ids = fields.One2many(
        'pi.product.warehouse.intelligence',
        'product_id',
        string='Inteligencia por Almacén'
    )
    
    # === INDICADORES DE RIESGO (GLOBAL) ===
    days_of_stock = fields.Float(
        string='Días de Stock (Global)',
        compute='_compute_stock_risk',
        store=True,
        help='Cuántos días puede durar el stock actual (Promedio Global)'
    )
    stockout_risk = fields.Selection([
        ('none', 'Sin Riesgo'),
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', 'CRÍTICO')
    ], string='Riesgo de Rotura (Global)', compute='_compute_stock_risk', store=True)
    
    needs_reorder = fields.Boolean(
        string='¿Necesita Pedido?',
        compute='_compute_stock_risk',
        store=True
    )
    suggested_order_qty = fields.Float(
        string='Cantidad Sugerida a Pedir',
        compute='_compute_stock_risk',
        store=True
    )

    # Métricas de rendimiento
    stock_turnover = fields.Float(string='Rotación de Inventario')
    days_inventory_outstanding = fields.Float(string='Días de Inventario (DIO)')
    
    # Para compatibilidad pero se computan
    safety_stock_suggested = fields.Float(related='safety_stock', string='Stock Seguridad Sugerido')
    reorder_point_suggested = fields.Float(related='reorder_point', string='Punto Reorden Sugerido')

    @api.depends('seller_ids.delay')
    def _compute_lead_time_days(self):
        for record in self:
            if record.seller_ids:
                record.lead_time_days = max(record.seller_ids.mapped('delay')) or 7
            else:
                record.lead_time_days = 7  # Default 7 días si no hay proveedor

    @api.depends('type')
    def _compute_is_storable(self):
        """Determine if product is storable"""
        for record in self:
            record.is_storable = record.type == 'product'

    @api.depends('standard_price', 'qty_available')
    def _compute_abc_classification(self):
        """Clasificación ABC basada en valor de inventario"""
        for record in self:
            value = (record.standard_price or 0) * (record.qty_available or 0)
            if value > 10000:
                record.abc_classification = 'A'
            elif value > 1000:
                record.abc_classification = 'B'
            else:
                record.abc_classification = 'C'

    @api.depends('daily_usage')
    def _compute_fsn_classification(self):
        """Clasificación basada en velocidad de movimiento"""
        for record in self:
            if record.daily_usage > 5:
                record.fsn_classification = 'F'  # Fast
            elif record.daily_usage > 1:
                record.fsn_classification = 'S'  # Slow
            elif record.daily_usage > 0:
                record.fsn_classification = 'N'  # Non-moving pero hay algo
            else:
                record.fsn_classification = 'D'  # Dead - sin movimiento

    def _compute_consumption_stats(self):
        """
        CÁLCULO AUTOMÁTICO: Analiza los movimientos de stock reales
        para calcular el consumo diario, semanal y mensual.
        AHORA SOPORTA CÁLCULO ESPECÍFICO POR ALMACÉN.
        """
        today = fields.Date.context_today(self)
        date_90_days_ago = today - timedelta(days=90)
        date_30_days_ago = today - timedelta(days=30)
        
        for record in self:
            # Determinar si tenemos contexto de almacén específico
            warehouse_filter = []
            if hasattr(self.env.context, 'warehouse_id') and self.env.context.get('warehouse_id'):
                warehouse_filter = [('location_id.warehouse_id', '=', self.env.context['warehouse_id'])]
            
            # Buscar movimientos de SALIDA de los últimos 90 días
            # (ventas, entregas a clientes, consumo interno)
            domain = [
                ('product_id.product_tmpl_id', '=', record.id),
                ('state', '=', 'done'),
                ('date', '>=', date_90_days_ago),
                ('location_id.usage', '=', 'internal'),  # Desde ubicación interna
                ('location_dest_id.usage', '!=', 'internal'),  # A ubicación no interna
            ] + warehouse_filter  # Aplicar filtro de almacén si existe
            
            moves_90 = self.env['stock.move'].search(domain)
            total_qty_90 = sum(moves_90.mapped('product_uom_qty'))
            
            # Consumo en últimos 30 días (más reciente)
            moves_30 = moves_90.filtered(lambda m: m.date.date() >= date_30_days_ago)
            total_qty_30 = sum(moves_30.mapped('product_uom_qty'))
            
            # Calcular promedios
            if total_qty_30 > 0:
                # Preferir datos de 30 días si hay suficiente actividad
                record.daily_usage = total_qty_30 / 30
                record.weekly_usage = total_qty_30 / 4.3  # 4.3 semanas en un mes
                record.monthly_usage = total_qty_30
            elif total_qty_90 > 0:
                # Usar 90 días si no hay datos recientes
                record.daily_usage = total_qty_90 / 90
                record.weekly_usage = total_qty_90 / 13  # 13 semanas en 90 días
                record.monthly_usage = total_qty_90 / 3
            else:
                record.daily_usage = 0
                record.weekly_usage = 0
                record.monthly_usage = 0

    @api.depends('daily_usage', 'lead_time_days', 'qty_available')
    def _compute_intelligent_stock_levels(self):
        """
        CÁLCULO AUTOMÁTICO de niveles de stock inteligentes:
        - Stock de Seguridad: Para cubrir variaciones
        - Punto de Reorden: Cuando pedir
        - Stock Máximo: Límite superior
        - EOQ: Cantidad óptima a pedir
        AHORA SOPORTA PARÁMETROS ESPECÍFICOS POR ALMACÉN.
        """
        # Obtener configuración global
        config = self.env['purchase.intelligence.config'].search([], limit=1)
        service_level = 1.65  # Factor para 95% de nivel de servicio
        holding_cost_pct = (config.holding_cost_percentage / 100) if config else 0.20
        ordering_cost = config.ordering_cost if config else 50
        
        for record in self:
            daily_usage = record.daily_usage or 0
            lead_time = record.lead_time_days or 7
            
            if daily_usage <= 0:
                record.safety_stock = 0
                record.reorder_point = 0
                record.max_stock = 0
                record.eoq = 0
                continue
            
            # === AJUSTES POR ALMACÉN ===
            # Si hay contexto de almacén, ajustar parámetros
            warehouse_adjustments = self._get_warehouse_adjustments(record)
            
            # === STOCK DE SEGURIDAD ===
            # SS = Z * σ * √L (donde Z es factor de servicio, σ es desviación, L es lead time)
            # Aproximación simple: 50% del consumo durante lead time con ajuste
            safety_stock = daily_usage * lead_time * 0.5 * warehouse_adjustments['safety_factor']
            
            # === PUNTO DE REORDEN ===
            # ROP = (Demanda Diaria × Lead Time) + Stock de Seguridad
            reorder_point = (daily_usage * lead_time * warehouse_adjustments['demand_factor']) + safety_stock
            
            # === EOQ (Cantidad Económica de Pedido) ===
            # EOQ = √((2 × D × S) / H)
            # D = demanda anual, S = costo por pedido, H = costo de mantener
            annual_demand = daily_usage * 365 * warehouse_adjustments['demand_factor']
            unit_cost = record.standard_price or 1
            holding_cost = unit_cost * holding_cost_pct * warehouse_adjustments['holding_factor']
            
            if holding_cost > 0:
                try:
                    eoq = math.sqrt((2 * annual_demand * ordering_cost) / holding_cost)
                except ValueError:
                    eoq = daily_usage * 30
            else:
                eoq = daily_usage * 30
            
            # Mínimo: al menos 1 semana de consumo
            eoq = max(eoq, daily_usage * 7 * warehouse_adjustments['order_quantity_factor'])
            
            # === STOCK MÁXIMO ===
            max_stock = reorder_point + eoq
            
            record.safety_stock = round(safety_stock, 2)
            record.reorder_point = round(reorder_point, 2)
            record.max_stock = round(max_stock, 2)
            record.eoq = round(eoq, 2)
            
            # === GENERAR INTELIGENCIA POR ALMACÉN ===
            # Solo si no estamos en un contexto de almacén específico
            # para evitar recursión o cálculos parciales
            if not self.env.context.get('warehouse_id'):
                record._generate_per_warehouse_intelligence()

    def _generate_per_warehouse_intelligence(self):
        """Genera/Actualiza registros de inteligencia para cada almacén"""
        WarehouseIntel = self.env['pi.product.warehouse.intelligence']
        # Filter only active warehouses for intelligence
        warehouses = self.env['stock.warehouse'].search([('active_intelligence', '=', True)])
        
        for warehouse in warehouses:
            # Calcular valores específicos para este almacén
            ctx = {'warehouse_id': warehouse.id}
            product_ctx = self.with_context(ctx)
            
            # Recalcular métricas en contexto de almacén
            # Nota: Esto es costoso, se debe optimizar en producción 
            # usando SQL directo o batch processing
            
            # 1. Consumo
            product_ctx._compute_consumption_stats()
            daily_usage = product_ctx.daily_usage
            
            # 2. Stock Levels
            # Replicamos lógica de _compute_intelligent_stock_levels pero con ajustes de almacén
            adjustments = self.with_context(ctx)._get_warehouse_adjustments(self)
            
            safety_stock = daily_usage * product_ctx.lead_time_days * 0.5 * adjustments['safety_factor']
            reorder_point = (daily_usage * product_ctx.lead_time_days * adjustments['demand_factor']) + safety_stock
            max_stock = reorder_point + (daily_usage * 30) # Simplificado para ejemplo
            
            # 3. Stock Actual
            qty_available = product_ctx.with_context(warehouse_id=warehouse.id).qty_available
            
            # 4. Dias de Stock
            days_of_stock = qty_available / daily_usage if daily_usage > 0 else 999.0
            
            # 5. Riesgo
            risk = 'none'
            if qty_available <= 0: risk = 'critical'
            elif qty_available <= safety_stock: risk = 'critical'
            elif qty_available <= reorder_point: risk = 'high'
            elif days_of_stock < 7: risk = 'low'
            
            # 6. Sugerencias
            needs_reorder = False
            suggested_qty = 0
            if risk in ['critical', 'high', 'low']: # Simplificado
                needs_reorder = True
                suggested_qty = max(product_ctx.eoq, reorder_point - qty_available)
                
            # 7. Clasificación (Simplificada, usando global como base pero se podría recalcular)
            abc = self.abc_classification
            fsn = self.fsn_classification
            ved = self.ved_classification
            
            # Crear/Actualizar registro
            intel_record = WarehouseIntel.search([
                ('product_id', '=', self.id),
                ('warehouse_id', '=', warehouse.id)
            ], limit=1)
            
            vals = {
                'product_id': self.id,
                'warehouse_id': warehouse.id,
                'daily_usage': daily_usage,
                'weekly_usage': product_ctx.weekly_usage,
                'monthly_usage': product_ctx.monthly_usage,
                'lead_time_days': product_ctx.lead_time_days,
                'safety_stock': safety_stock,
                'reorder_point': reorder_point,
                'max_stock': max_stock,
                'eoq': product_ctx.eoq,
                'qty_available': qty_available,
                'days_of_stock': days_of_stock,
                'stockout_risk': risk,
                'needs_reorder': needs_reorder,
                'suggested_order_qty': suggested_qty,
                'abc_classification': abc,
                'fsn_classification': fsn,
                'ved_classification': ved,
            }
            
            if intel_record:
                intel_record.write(vals)
            else:
                WarehouseIntel.create(vals)
    
    def _get_warehouse_adjustments(self, record):
        """
        Obtener factores de ajuste específicos por almacén
        """
        # Valores por defecto (sin ajuste)
        default_adjustments = {
            'safety_factor': 1.0,
            'demand_factor': 1.0,
            'holding_factor': 1.0,
            'order_quantity_factor': 1.0,
        }
        
        # Si no hay contexto de almacén, retornar valores por defecto
        if not hasattr(self.env.context, 'warehouse_id') or not self.env.context.get('warehouse_id'):
            return default_adjustments
        
        warehouse_id = self.env.context['warehouse_id']
        warehouse = self.env['stock.warehouse'].browse(warehouse_id)
        
        if not warehouse.exists():
            return default_adjustments
        
        # Factores de ajuste basados en características del almacén
        # Estos pueden ser configurables en el futuro
        warehouse_factors = {
            'main_warehouse': {
                'safety_factor': 1.0,      # Stock estándar
                'demand_factor': 1.0,       # Demanda estable
                'holding_factor': 1.0,       # Costos estándar
                'order_quantity_factor': 1.0, # Cantidades estándar
            },
            'secondary_warehouse': {
                'safety_factor': 1.2,      # 20% más stock de seguridad
                'demand_factor': 0.9,       # Demanda ligeramente menor
                'holding_factor': 1.1,       # 10% más costo de mantenimiento
                'order_quantity_factor': 0.8, # Órdenes más pequeñas
            },
            'regional_warehouse': {
                'safety_factor': 1.5,      # 50% más stock de seguridad
                'demand_factor': 0.8,       # Demanda variable
                'holding_factor': 1.2,       # 20% más costo de mantenimiento
                'order_quantity_factor': 0.7, # Órdenes más pequeñas
            },
        }
        
        # Obtener factores basados en el tipo de almacén (si el campo existe, sino usar default)
        warehouse_type = getattr(warehouse, 'warehouse_type', None) or 'main_warehouse'
        return warehouse_factors.get(warehouse_type, default_adjustments)

    @api.depends('qty_available', 'daily_usage', 'reorder_point', 'safety_stock', 'eoq', 'max_stock')
    def _compute_stock_risk(self):
        """
        CÁLCULO AUTOMÁTICO de riesgo de stockout y sugerencias de pedido
        AHORA SOPORTA ANÁLISIS ESPECÍFICO POR ALMACÉN.
        """
        for record in self:
            daily_usage = record.daily_usage or 0
            qty_available = record.qty_available or 0
            reorder_point = record.reorder_point or 0
            safety_stock = record.safety_stock or 0
            eoq = record.eoq or 0
            max_stock = record.max_stock or 0
            
            # === STOCK ESPECÍFICO POR ALMACÉN ===
            warehouse_stock = self._get_warehouse_stock(record)
            if warehouse_stock is not None:
                qty_available = warehouse_stock
                # Recalcular días de stock con stock específico del almacén
                days_of_stock = qty_available / daily_usage if daily_usage > 0 else 999
            else:
                # Usar stock global si no hay contexto de almacén
                days_of_stock = qty_available / daily_usage if daily_usage > 0 else 999
            
            record.days_of_stock = round(days_of_stock, 1)
            
            # === ANÁLISIS DE RIESGO ESPECÍFICO POR ALMACÉN ===
            # Determinar nivel de riesgo basado en stock específico del almacén
            if daily_usage <= 0:
                record.stockout_risk = 'none'
                record.needs_reorder = False
                record.suggested_order_qty = 0
            elif qty_available <= 0:
                record.stockout_risk = 'critical'
                record.needs_reorder = True
                record.suggested_order_qty = max_stock
            elif qty_available <= safety_stock:
                record.stockout_risk = 'critical'
                record.needs_reorder = True
                record.suggested_order_qty = max_stock - qty_available
            elif qty_available <= reorder_point:
                if days_of_stock < 3:
                    record.stockout_risk = 'high'
                else:
                    record.stockout_risk = 'medium'
                record.needs_reorder = True
                record.suggested_order_qty = max(eoq, max_stock - qty_available)
            elif days_of_stock < 7:
                record.stockout_risk = 'low'
                record.needs_reorder = True
                record.suggested_order_qty = eoq
            else:
                record.stockout_risk = 'none'
                record.needs_reorder = False
                record.suggested_order_qty = 0
    
    def _get_warehouse_stock(self, record):
        """
        Obtener stock específico del producto en el almacén del contexto
        """
        # Si no hay contexto de almacén, retornar None (usará stock global)
        if not hasattr(self.env.context, 'warehouse_id') or not self.env.context.get('warehouse_id'):
            return None
        
        warehouse_id = self.env.context['warehouse_id']
        
        # Buscar stock específico en este almacén
        stock_quant = self.env['stock.quant'].search([
            ('product_id', '=', record.id),
            ('location_id.warehouse_id', '=', warehouse_id),
            ('quantity', '>', 0)
        ], limit=1)
        
        return stock_quant.quantity if stock_quant else None

    @api.model
    def action_recalculate_all_stock_intelligence(self):
        """
        Método Cron para recalcular toda la inteligencia de stock.
        Se ejecuta automáticamente todos los días.
        """
        _logger.info("=== Iniciando cálculo automático de inteligencia de stock ===")
        
        products = self.search([('is_storable', '=', True)])
        
        for product in products:
            # Forzar recálculo
            product._compute_consumption_stats()
            product._compute_intelligent_stock_levels()
            product._compute_stock_risk()
        
        # Generar sugerencias automáticas
        products_need_reorder = products.filtered(lambda p: p.needs_reorder)
        
        _logger.info(f"Productos analizados: {len(products)}")
        _logger.info(f"Productos que necesitan pedido: {len(products_need_reorder)}")
        
        # Crear sugerencias automáticas
        AutoOrder = self.env['pi.automated.order']
        for product in products_need_reorder:
            # Verificar si ya existe sugerencia activa
            existing = AutoOrder.search([
                ('product_id', 'in', product.product_variant_ids.ids),
                ('state', 'in', ['draft', 'suggested', 'approved'])
            ], limit=1)
            
            if not existing and product.suggested_order_qty > 0:
                variant = product.product_variant_ids[0] if product.product_variant_ids else None
                if variant:
                    supplier = product.seller_ids[0].partner_id if product.seller_ids else False
                    
                    # Determinar urgencia
                    if product.stockout_risk == 'critical':
                        urgency = 'critical'
                    elif product.stockout_risk == 'high':
                        urgency = 'high'
                    elif product.stockout_risk == 'medium':
                        urgency = 'medium'
                    else:
                        urgency = 'low'
                    
                    AutoOrder.create({
                        'product_id': variant.id,
                        'suggested_qty': product.suggested_order_qty,
                        'supplier_id': supplier.id if supplier else False,
                        'urgency': urgency,
                        'state': 'suggested',
                        'current_stock': product.qty_available,
                        'min_stock': product.safety_stock,
                        'reorder_point': product.reorder_point,
                        'daily_usage': product.daily_usage,
                        'lead_time_days': product.lead_time_days,
                        'reason': f"""ANÁLISIS AUTOMÁTICO:
• Stock Actual: {product.qty_available} unidades
• Consumo Diario: {product.daily_usage:.2f} unidades
• Días de Stock: {product.days_of_stock:.1f} días
• Punto de Reorden: {product.reorder_point:.1f}
• Stock de Seguridad: {product.safety_stock:.1f}
• Tiempo de Entrega: {product.lead_time_days} días

⚠️ ACCIÓN: Pedir {product.suggested_order_qty:.0f} unidades para evitar rotura de stock.""",
                    })
        
        _logger.info(f"Sugerencias creadas automáticamente")
        return True


class ProductProduct(models.Model):
    """Heredar campos en variantes de producto"""
    _inherit = 'product.product'
    
    # Los campos en product.template se heredan automáticamente
    # Pero necesitamos asegurar que las búsquedas funcionen
    
    is_storable = fields.Boolean(related='product_tmpl_id.is_storable', store=True)
    abc_classification = fields.Selection(related='product_tmpl_id.abc_classification', store=True)
    stockout_risk = fields.Selection(related='product_tmpl_id.stockout_risk', store=True)
    needs_reorder = fields.Boolean(related='product_tmpl_id.needs_reorder', store=True)
    days_of_stock = fields.Float(related='product_tmpl_id.days_of_stock', store=True)
    daily_usage = fields.Float(related='product_tmpl_id.daily_usage', store=True)
    reorder_point_suggested = fields.Float(related='product_tmpl_id.reorder_point', store=True)
    warehouse_intelligence_ids = fields.One2many(related='product_tmpl_id.warehouse_intelligence_ids', readonly=True)


