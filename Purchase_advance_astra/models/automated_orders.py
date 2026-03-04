# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta

class PIAutomatedOrder(models.Model):
    _name = 'pi.automated.order'
    _description = 'Órdenes de Compra Automatizadas'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string='Referencia', required=True, default='Nuevo', copy=False)
    date = fields.Datetime(string='Fecha de Creación', default=fields.Datetime.now, required=True)
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    suggested_qty = fields.Float(string='Cantidad Sugerida', required=True)
    supplier_id = fields.Many2one('res.partner', string='Proveedor Sugerido', domain=[('supplier_rank', '>', 0)])
    
    urgency = fields.Selection([
        ('low', 'Baja'),
        ('medium', 'Media'),
        ('high', 'Alta'),
        ('critical', 'Crítica')
    ], string='Urgencia', default='medium', required=True)
    
    reason = fields.Text(string='Razón de la Sugerencia')
    
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('suggested', 'Sugerido'),
        ('approved', 'Aprobado'),
        ('rejected', 'Rechazado'),
        ('created', 'PO Creada')
    ], string='Estado', default='draft', tracking=True)
    
    purchase_order_id = fields.Many2one('purchase.order', string='Orden de Compra', readonly=True)
    
    # Datos de cálculo
    current_stock = fields.Float(string='Stock Actual')
    min_stock = fields.Float(string='Stock Mínimo')
    reorder_point = fields.Float(string='Punto de Reorden')
    lead_time_days = fields.Integer(string='Tiempo de Entrega (Días)')
    daily_usage = fields.Float(string='Uso Diario')
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'Nuevo') == 'Nuevo':
                vals['name'] = self.env['ir.sequence'].next_by_code('pi.automated.order') or 'Nuevo'
        return super(PIAutomatedOrder, self).create(vals_list)
    
    def action_create_purchase_order(self):
        """Crear orden de compra desde la sugerencia - usado por el dashboard"""
        return self.action_approve()
    
    def action_approve(self):
        """Aprobar la sugerencia y crear orden de compra"""
        self.ensure_one()
        if not self.supplier_id:
            raise UserError('Debe seleccionar un proveedor antes de aprobar.')
        
        # Crear orden de compra
        po_vals = {
            'partner_id': self.supplier_id.id,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.suggested_qty,
                'price_unit': self.product_id.standard_price,
                'date_planned': fields.Datetime.now() + timedelta(days=self.lead_time_days),
            })],
            'notes': f'Orden automática generada por: {self.name}\nRazón: {self.reason}',
        }
        
        po = self.env['purchase.order'].create(po_vals)
        
        self.write({
            'state': 'created',
            'purchase_order_id': po.id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_reject(self):
        """Rechazar la sugerencia"""
        self.write({'state': 'rejected'})

    def action_view_purchase_order(self):
        """Abrir la orden de compra relacionada"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': self.purchase_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    @api.model
    def generate_automated_suggestions(self):
        """
        Método Cron: Generar sugerencias de órdenes automáticas
        Basado en puntos de reorden y stock actual
        """
        products = self.env['product.product'].search([
            ('is_storable', '=', True),
            ('purchase_ok', '=', True)
        ])
        
        suggestions_created = 0
        for product in products:
            # Verificar si ya existe una sugerencia activa
            existing = self.search([
                ('product_id', '=', product.id),
                ('state', 'in', ['draft', 'suggested', 'approved'])
            ], limit=1)
            
            if existing:
                continue
            
            # Calcular si necesita reorden
            current_stock = product.qty_available
            reorder_point = product.reorder_point_suggested or 0
            
            if current_stock <= reorder_point and reorder_point > 0:
                # Determinar urgencia
                days_of_stock = current_stock / product.daily_usage if product.daily_usage > 0 else 999
                
                if days_of_stock < 1:
                    urgency = 'critical'
                elif days_of_stock < 3:
                    urgency = 'high'
                elif days_of_stock < 7:
                    urgency = 'medium'
                else:
                    urgency = 'low'
                
                # Obtener proveedor preferido
                supplier = product.seller_ids[0].partner_id if product.seller_ids else False
                
                # Calcular cantidad sugerida (EOQ o cantidad mínima)
                suggested_qty = product.eoq if product.eoq > 0 else (reorder_point - current_stock) * 2
                
                # Crear sugerencia
                self.create({
                    'product_id': product.id,
                    'suggested_qty': suggested_qty,
                    'supplier_id': supplier.id if supplier else False,
                    'urgency': urgency,
                    'reason': f'Stock actual ({current_stock}) por debajo del punto de reorden ({reorder_point}). Días de stock restantes: {days_of_stock:.1f}',
                    'state': 'suggested',
                    'current_stock': current_stock,
                    'reorder_point': reorder_point,
                    'lead_time_days': product.lead_time_days,
                    'daily_usage': product.daily_usage,
                })
                
                suggestions_created += 1
        
        return suggestions_created


class PIReorderOptimization(models.Model):
    _name = 'pi.reorder.optimization'
    _description = 'Optimización de Reorden'
    
    product_id = fields.Many2one('product.product', string='Producto', required=True)
    date = fields.Date(string='Fecha de Análisis', default=fields.Date.context_today)
    
    # Parámetros actuales
    current_rop = fields.Float(string='ROP Actual')
    current_eoq = fields.Float(string='EOQ Actual')
    current_safety_stock = fields.Float(string='Stock de Seguridad Actual')
    
    # Parámetros optimizados
    optimized_rop = fields.Float(string='ROP Optimizado')
    optimized_eoq = fields.Float(string='EOQ Optimizado')
    optimized_safety_stock = fields.Float(string='Stock de Seguridad Optimizado')
    
    # Métricas de rendimiento
    stockout_risk = fields.Float(string='Riesgo de Rotura (%)')
    carrying_cost = fields.Float(string='Costo de Mantenimiento')
    ordering_cost = fields.Float(string='Costo de Pedido')
    total_cost = fields.Float(string='Costo Total')
    
    # Recomendaciones
    recommendation = fields.Text(string='Recomendación')
    applied = fields.Boolean(string='Aplicado', default=False)
    
    @api.model
    def action_generate_all_optimizations(self):
        """
        MÉTODO AUTOMÁTICO: Genera optimizaciones de reorden para TODOS los productos
        usando los datos reales del sistema (consumo, stock, tiempos de entrega)
        """
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info("=== Iniciando generación automática de optimizaciones de reorden ===")
        
        products = self.env['product.product'].search([
            ('is_storable', '=', True),
            ('purchase_ok', '=', True)
        ])
        
        today = fields.Date.context_today(self)
        created_count = 0
        updated_count = 0
        
        for product in products:
            # Buscar si ya existe una optimización para este producto recientemente (últimos 2 días)
            # El cron corre cada 3 días, así que si hay una de hace < 3 días es la "actual".
            existing = self.search([
                ('product_id', '=', product.id),
                ('date', '>=', today - timedelta(days=2))
            ], limit=1)
            
            # Calcular datos desde el sistema
            daily_usage = product.daily_usage or 0
            lead_time = product.lead_time_days or 7
            
            # Calcular ROP (Reorder Point) = Demanda durante lead time + Safety Stock
            # Safety Stock = Z * σ * √L (donde Z=1.65 para 95% servicio)
            avg_demand = daily_usage * lead_time
            safety_factor = 1.65  # 95% nivel de servicio
            
            # Calcular variabilidad de demanda
            # Usamos el 20% del consumo promedio como desviación estándar estimada
            demand_std = daily_usage * 0.20
            safety_stock = safety_factor * demand_std * (lead_time ** 0.5)
            
            optimized_rop = avg_demand + safety_stock
            
            # Calcular EOQ (Economic Order Quantity)
            # EOQ = √(2DS/H) donde D=demanda anual, S=costo de pedido, H=costo mantenimiento
            annual_demand = daily_usage * 365
            ordering_cost = 50  # Costo estimado por orden
            holding_cost_rate = 0.25  # 25% del costo del producto
            unit_cost = product.standard_price or 1
            holding_cost = unit_cost * holding_cost_rate
            
            if annual_demand > 0 and holding_cost > 0:
                optimized_eoq = ((2 * annual_demand * ordering_cost) / holding_cost) ** 0.5
            else:
                optimized_eoq = daily_usage * 30  # Pedido mensual por defecto
            
            # Calcular métricas
            current_stock = product.qty_available
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
            
            # Generar recomendación automática
            recommendations = []
            if current_stock < optimized_rop:
                recommendations.append(f"⚠️ URGENTE: Stock actual ({current_stock:.0f}) está por debajo del punto de reorden optimizado ({optimized_rop:.0f})")
            if daily_usage > 0 and days_of_stock < lead_time:
                recommendations.append(f"🔴 CRÍTICO: Solo {days_of_stock:.1f} días de stock, pero el tiempo de entrega es {lead_time} días")
            if product.eoq and abs(product.eoq - optimized_eoq) / max(1, product.eoq) > 0.2:
                recommendations.append(f"📊 Ajustar EOQ de {product.eoq:.0f} a {optimized_eoq:.0f} para optimizar costos")
            if safety_stock > 0:
                recommendations.append(f"🛡️ Mantener {safety_stock:.0f} unidades de stock de seguridad")
            
            if not recommendations:
                recommendations.append("✅ Parámetros de inventario optimizados. Sin acciones requeridas.")
            
            vals = {
                'product_id': product.id,
                'date': today,
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
                'recommendation': '\n'.join(recommendations),
            }
            
            if existing:
                existing.write(vals)
                updated_count += 1
            else:
                self.create(vals)
                created_count += 1
        
        _logger.info(f"Optimizaciones generadas: {created_count} nuevas, {updated_count} actualizadas")
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Optimización Completada',
                'message': f'Se han generado {created_count} nuevas optimizaciones y actualizado {updated_count}.',
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }
            }
        }
    
    def action_apply_optimization(self):
        """Aplicar los valores optimizados al producto"""
        for record in self:
            if record.product_id:
                record.product_id.product_tmpl_id.write({
                    'reorder_point': record.optimized_rop,
                    'eoq': record.optimized_eoq,
                    'safety_stock': record.optimized_safety_stock,
                })
                record.applied = True
        return True


class PIContractPerformance(models.Model):
    _name = 'pi.contract.performance'
    _description = 'Rendimiento de Contratos'
    
    name = fields.Char(string='Nombre del Contrato', required=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', required=True)
    
    start_date = fields.Date(string='Fecha de Inicio', required=True)
    end_date = fields.Date(string='Fecha de Fin', required=True)
    
    contract_value = fields.Float(string='Valor del Contrato')
    utilized_value = fields.Float(string='Valor Utilizado', compute='_compute_utilization')
    utilization_percent = fields.Float(string='% Utilización', compute='_compute_utilization')
    
    savings_amount = fields.Float(string='Ahorros Generados')
    
    state = fields.Selection([
        ('active', 'Activo'),
        ('expiring', 'Por Vencer'),
        ('expired', 'Vencido'),
        ('renewed', 'Renovado')
    ], string='Estado', default='active')
    
    @api.depends('contract_value')
    def _compute_utilization(self):
        for record in self:
            # Calcular valor utilizado basado en órdenes de compra
            pos = self.env['purchase.order'].search([
                ('partner_id', '=', record.partner_id.id),
                ('date_order', '>=', record.start_date),
                ('date_order', '<=', record.end_date),
                ('state', 'in', ['purchase', 'done'])
            ])
            
            record.utilized_value = sum(pos.mapped('amount_total'))
            record.utilization_percent = (record.utilized_value / record.contract_value * 100) if record.contract_value else 0
