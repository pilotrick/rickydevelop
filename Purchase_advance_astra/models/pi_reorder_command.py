# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo 19 - Purchase Intelligence Module
#    Centro de Comando de Reorden - ¿Qué Pedir Ahora?
#
##############################################################################

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class PIReorderCommand(models.Model):
    """
    Centro de Comando de Reorden - Vista Unificada de TODO lo que hay que pedir
    """
    _name = 'pi.reorder.command'
    _description = 'Centro de Comando de Reorden'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'priority_score desc, days_until_stockout asc'
    _rec_name = 'product_id'

    # === Campos Principales ===
    product_id = fields.Many2one(
        'product.product',
        string='Producto',
        required=True,
        ondelete='cascade',
        index=True
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Plantilla de Producto',
        related='product_id.product_tmpl_id',
        store=True
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Proveedor Sugerido',
        compute='_compute_supplier',
        store=True
    )
    category_id = fields.Many2one(
        'product.category',
        string='Categoría',
        related='product_id.categ_id',
        store=True
    )
    
    # === Métricas de Stock ===
    total_stock = fields.Float(
        string='Stock Total',
        compute='_compute_stock_metrics',
        store=True,
        help='Stock disponible en todos los almacenes'
    )
    total_virtual_stock = fields.Float(
        string='Stock Virtual',
        compute='_compute_stock_metrics',
        store=True,
        help='Stock total + entrante - saliente'
    )
    warehouses_with_low_stock = fields.Integer(
        string='Almacenes con Stock Bajo',
        compute='_compute_stock_metrics',
        store=True
    )
    warehouses_with_zero_stock = fields.Integer(
        string='Almacenes sin Stock',
        compute='_compute_stock_metrics',
        store=True
    )
    
    # === Métricas de Demanda ===
    daily_usage = fields.Float(
        string='Consumo Diario',
        compute='_compute_demand_metrics',
        store=True
    )
    weekly_sales = fields.Float(
        string='Ventas Últimos 7 Días',
        compute='_compute_demand_metrics',
        store=True
    )
    monthly_sales = fields.Float(
        string='Ventas Últimos 30 Días',
        compute='_compute_demand_metrics',
        store=True
    )
    
    # === Pipeline de Ventas (NUEVO) ===
    pending_quotations_qty = fields.Float(
        string='Cantidad en Cotizaciones',
        compute='_compute_sales_pipeline',
        store=True,
        help='Cantidad en cotizaciones pendientes de confirmar'
    )
    pending_quotations_amount = fields.Monetary(
        string='Valor en Cotizaciones',
        compute='_compute_sales_pipeline',
        store=True,
        currency_field='currency_id'
    )
    confirmed_orders_qty = fields.Float(
        string='Cantidad Confirmada Sin Entregar',
        compute='_compute_sales_pipeline',
        store=True,
        help='Cantidad en órdenes confirmadas pendientes de entrega'
    )
    confirmed_orders_amount = fields.Monetary(
        string='Valor Confirmado Sin Entregar',
        compute='_compute_sales_pipeline',
        store=True,
        currency_field='currency_id'
    )
    total_demand = fields.Float(
        string='Demanda Total Pipeline',
        compute='_compute_sales_pipeline',
        store=True,
        help='Cotizaciones + Órdenes confirmadas sin entregar'
    )
    
    # === Riesgo de Ventas Perdidas ===
    lost_sales_risk_qty = fields.Float(
        string='Riesgo Ventas Perdidas (Cant)',
        compute='_compute_lost_sales_risk',
        store=True,
        help='Cantidad de demanda que no se puede cubrir con el stock actual'
    )
    lost_sales_risk_amount = fields.Monetary(
        string='Riesgo Ventas Perdidas ($)',
        compute='_compute_lost_sales_risk',
        store=True,
        currency_field='currency_id'
    )
    
    # === Proyecciones ===
    days_until_stockout = fields.Float(
        string='Días Hasta Agotarse',
        compute='_compute_projections',
        store=True,
        help='Días de stock restantes al ritmo actual de consumo'
    )
    projected_stockout_date = fields.Date(
        string='Fecha Proyectada de Agotamiento',
        compute='_compute_projections',
        store=True
    )
    lead_time_days = fields.Float(
        string='Tiempo de Entrega (días)',
        compute='_compute_supplier',
        store=True
    )
    
    # === Recomendación de Compra ===
    suggested_order_qty = fields.Float(
        string='Cantidad Sugerida a Pedir',
        compute='_compute_recommendation',
        store=True
    )
    suggested_order_amount = fields.Monetary(
        string='Monto Sugerido',
        compute='_compute_recommendation',
        store=True,
        currency_field='currency_id'
    )
    last_purchase_price = fields.Float(
        string='Último Precio de Compra',
        compute='_compute_supplier',
        store=True
    )
    
    # === Priorización ===
    priority_score = fields.Float(
        string='Puntuación de Prioridad',
        compute='_compute_priority',
        store=True,
        help='Score 0-100 basado en urgencia, riesgo de ventas perdidas y cantidad de almacenes afectados'
    )
    urgency_level = fields.Selection([
        ('critical', '🔴 Crítico'),
        ('high', '🟠 Alto'),
        ('medium', '🟡 Medio'),
        ('low', '🟢 Bajo'),
    ], string='Nivel de Urgencia', compute='_compute_priority', store=True)
    
    # === Estado ===
    state = fields.Selection([
        ('pending', 'Pendiente'),
        ('po_created', 'OC Creada'),
        ('ignored', 'Ignorado'),
    ], string='Estado', default='pending')
    
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Orden de Compra Creada'
    )
    
    last_refresh = fields.Datetime(
        string='Última Actualización',
        default=fields.Datetime.now
    )
    
    # === Detalle por Almacén ===
    warehouse_detail_ids = fields.One2many(
        'pi.reorder.command.warehouse',
        'command_id',
        string='Detalle por Almacén'
    )
    warehouse_detail_html = fields.Html(
        string='Stock por Almacén',
        compute='_compute_warehouse_html'
    )
    
    # === Campos Auxiliares ===
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        default=lambda self: self.env.company
    )
    active = fields.Boolean(default=True)
    
    # === Métodos de Cálculo ===
    
    @api.depends('product_id')
    def _compute_supplier(self):
        """Obtener el proveedor preferido y su información"""
        for record in self:
            if not record.product_id:
                record.supplier_id = False
                record.lead_time_days = 0
                record.last_purchase_price = 0
                continue
            
            # Buscar el seller preferido
            seller = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', record.product_id.product_tmpl_id.id)
            ], order='sequence, min_qty', limit=1)
            
            if seller:
                record.supplier_id = seller.partner_id
                record.lead_time_days = seller.delay or 7
                record.last_purchase_price = seller.price or 0
            else:
                # Buscar última compra
                last_pol = self.env['purchase.order.line'].search([
                    ('product_id', '=', record.product_id.id),
                    ('order_id.state', 'in', ['purchase', 'done'])
                ], order='create_date desc', limit=1)
                
                if last_pol:
                    record.supplier_id = last_pol.partner_id
                    record.lead_time_days = 7
                    record.last_purchase_price = last_pol.price_unit
                else:
                    record.supplier_id = False
                    record.lead_time_days = 7
                    record.last_purchase_price = record.product_id.standard_price

    @api.depends('product_id')
    def _compute_stock_metrics(self):
        """Calcular métricas de stock en todos los almacenes"""
        for record in self:
            if not record.product_id:
                record.total_stock = 0
                record.total_virtual_stock = 0
                record.warehouses_with_low_stock = 0
                record.warehouses_with_zero_stock = 0
                continue
            
            product = record.product_id
            warehouses = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ])
            
            total_stock = 0
            total_virtual = 0
            low_stock_count = 0
            zero_stock_count = 0
            
            for wh in warehouses:
                # Stock en ubicación del almacén
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', wh.lot_stock_id.id),
                ])
                wh_stock = sum(quant.mapped('quantity'))
                wh_reserved = sum(quant.mapped('reserved_quantity'))
                wh_available = wh_stock - wh_reserved
                
                total_stock += wh_available
                
                # Stock virtual (incluye órdenes entrantes/salientes)
                product_wh = product.with_context(warehouse=wh.id)
                total_virtual += product_wh.virtual_available
                
                # Verificar niveles
                if wh_available <= 0:
                    zero_stock_count += 1
                elif wh_available < (product.reorder_point or 10):
                    low_stock_count += 1
            
            record.total_stock = total_stock
            record.total_virtual_stock = total_virtual
            record.warehouses_with_low_stock = low_stock_count
            record.warehouses_with_zero_stock = zero_stock_count

    @api.depends('product_id')
    def _compute_demand_metrics(self):
        """Calcular métricas de demanda basadas en historial"""
        today = fields.Date.today()
        for record in self:
            if not record.product_id:
                record.daily_usage = 0
                record.weekly_sales = 0
                record.monthly_sales = 0
                continue
            
            # Movimientos de salida (ventas) últimos 30 días
            moves = self.env['stock.move'].search([
                ('product_id', '=', record.product_id.id),
                ('state', '=', 'done'),
                ('location_dest_id.usage', '=', 'customer'),
                ('date', '>=', today - timedelta(days=30))
            ])
            
            monthly_qty = sum(moves.mapped('quantity'))
            
            # Últimos 7 días
            moves_week = moves.filtered(
                lambda m: m.date.date() >= today - timedelta(days=7)
            )
            weekly_qty = sum(moves_week.mapped('quantity'))
            
            record.monthly_sales = monthly_qty
            record.weekly_sales = weekly_qty
            record.daily_usage = monthly_qty / 30 if monthly_qty > 0 else 0

    @api.depends('product_id')
    def _compute_sales_pipeline(self):
        """Calcular demanda pendiente del pipeline de ventas"""
        for record in self:
            if not record.product_id:
                record.pending_quotations_qty = 0
                record.pending_quotations_amount = 0
                record.confirmed_orders_qty = 0
                record.confirmed_orders_amount = 0
                record.total_demand = 0
                continue
            
            product = record.product_id
            
            # Cotizaciones pendientes (draft, sent)
            quote_lines = self.env['sale.order.line'].search([
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ['draft', 'sent'])
            ])
            record.pending_quotations_qty = sum(quote_lines.mapped('product_uom_qty'))
            record.pending_quotations_amount = sum(quote_lines.mapped('price_subtotal'))
            
            # Órdenes confirmadas sin entregar completamente
            confirmed_lines = self.env['sale.order.line'].search([
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'done']),
            ]).filtered(lambda l: l.qty_delivered < l.product_uom_qty)
            # Cantidad pendiente de entregar
            pending_delivery = sum(
                line.product_uom_qty - line.qty_delivered 
                for line in confirmed_lines
            )
            record.confirmed_orders_qty = pending_delivery
            record.confirmed_orders_amount = sum(
                (line.product_uom_qty - line.qty_delivered) * line.price_unit 
                for line in confirmed_lines
            )
            
            record.total_demand = record.pending_quotations_qty + record.confirmed_orders_qty

    @api.depends('total_stock', 'total_demand', 'last_purchase_price')
    def _compute_lost_sales_risk(self):
        """Calcular el riesgo de ventas perdidas"""
        for record in self:
            shortage = record.total_demand - record.total_stock
            if shortage > 0:
                record.lost_sales_risk_qty = shortage
                # Usar precio de venta si disponible, sino precio de compra * margen
                product = record.product_id
                sale_price = product.list_price if product else 0
                record.lost_sales_risk_amount = shortage * (sale_price or record.last_purchase_price * 1.3)
            else:
                record.lost_sales_risk_qty = 0
                record.lost_sales_risk_amount = 0

    @api.depends('total_stock', 'daily_usage', 'lead_time_days')
    def _compute_projections(self):
        """Calcular proyecciones de agotamiento"""
        today = fields.Date.today()
        for record in self:
            if record.daily_usage > 0:
                days = record.total_stock / record.daily_usage
                record.days_until_stockout = days
                record.projected_stockout_date = today + timedelta(days=int(days))
            else:
                record.days_until_stockout = 999  # Sin movimiento
                record.projected_stockout_date = False

    @api.depends('total_stock', 'daily_usage', 'lead_time_days', 'lost_sales_risk_qty')
    def _compute_recommendation(self):
        """Calcular la cantidad recomendada a pedir"""
        for record in self:
            product = record.product_id
            if not product:
                record.suggested_order_qty = 0
                record.suggested_order_amount = 0
                continue
            
            # Stock objetivo = Cobertura de 30 días + Stock de seguridad
            target_days = 30
            safety_stock = record.daily_usage * 7  # 1 semana de seguridad
            
            target_stock = (record.daily_usage * target_days) + safety_stock
            
            # Considerar también la demanda del pipeline
            pipeline_need = max(0, record.total_demand - record.total_stock)
            
            # Cantidad a pedir
            qty_needed = max(0, target_stock - record.total_stock + pipeline_need)
            
            # Respetar MOQ del proveedor
            seller = self.env['product.supplierinfo'].search([
                ('product_tmpl_id', '=', product.product_tmpl_id.id)
            ], order='sequence, min_qty', limit=1)
            
            moq = seller.min_qty if seller else 1
            if qty_needed > 0 and qty_needed < moq:
                qty_needed = moq
                
            record.suggested_order_qty = qty_needed
            record.suggested_order_amount = qty_needed * record.last_purchase_price

    @api.depends('days_until_stockout', 'lead_time_days', 'lost_sales_risk_amount', 
                 'warehouses_with_zero_stock', 'warehouses_with_low_stock')
    def _compute_priority(self):
        """Calcular score de prioridad y nivel de urgencia"""
        for record in self:
            score = 0
            
            # Factor 1: Urgencia por días de stock (40% del score)
            if record.days_until_stockout <= 0:
                urgency_score = 100
            elif record.days_until_stockout <= record.lead_time_days:
                urgency_score = 90
            elif record.days_until_stockout <= record.lead_time_days * 1.5:
                urgency_score = 70
            elif record.days_until_stockout <= record.lead_time_days * 2:
                urgency_score = 50
            else:
                urgency_score = 20
            score += urgency_score * 0.4
            
            # Factor 2: Riesgo de ventas perdidas (35% del score)
            if record.lost_sales_risk_amount > 10000:
                risk_score = 100
            elif record.lost_sales_risk_amount > 5000:
                risk_score = 80
            elif record.lost_sales_risk_amount > 1000:
                risk_score = 60
            elif record.lost_sales_risk_amount > 0:
                risk_score = 40
            else:
                risk_score = 0
            score += risk_score * 0.35
            
            # Factor 3: Almacenes afectados (25% del score)
            warehouse_score = min(100, (record.warehouses_with_zero_stock * 30) + 
                                       (record.warehouses_with_low_stock * 15))
            score += warehouse_score * 0.25
            
            record.priority_score = score
            
            # Determinar nivel de urgencia
            if score >= 80:
                record.urgency_level = 'critical'
            elif score >= 60:
                record.urgency_level = 'high'
            elif score >= 40:
                record.urgency_level = 'medium'
            else:
                record.urgency_level = 'low'

    @api.depends('product_id')
    def _compute_warehouse_html(self):
        """Generar HTML visual del stock por almacén"""
        for record in self:
            if not record.product_id:
                record.warehouse_detail_html = '<p>Sin producto seleccionado</p>'
                continue
            
            product = record.product_id
            warehouses = self.env['stock.warehouse'].search([
                ('company_id', '=', self.env.company.id)
            ])
            
            html_parts = ['<div class="row">']
            for wh in warehouses:
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id),
                    ('location_id', 'child_of', wh.lot_stock_id.id),
                ])
                stock = sum(quant.mapped('quantity')) - sum(quant.mapped('reserved_quantity'))
                
                # Determinar color
                if stock <= 0:
                    color = 'danger'
                    icon = '🔴'
                elif stock < (product.reorder_point or 10):
                    color = 'warning'
                    icon = '🟡'
                else:
                    color = 'success'
                    icon = '🟢'
                
                html_parts.append(f'''
                    <div class="col-md-4 mb-2">
                        <div class="card border-{color}">
                            <div class="card-body p-2">
                                <h6 class="mb-1">{icon} {wh.name}</h6>
                                <h4 class="text-{color} mb-0">{stock:.0f}</h4>
                            </div>
                        </div>
                    </div>
                ''')
            
            html_parts.append('</div>')
            record.warehouse_detail_html = ''.join(html_parts)

    # === Acciones ===
    
    def action_create_purchase_order(self):
        """Crear orden de compra para este producto"""
        self.ensure_one()
        
        if not self.supplier_id:
            raise UserError(_('No hay proveedor definido para este producto.'))
        
        if self.suggested_order_qty <= 0:
            raise UserError(_('La cantidad sugerida debe ser mayor a 0.'))
        
        # Crear la orden de compra
        po_vals = {
            'partner_id': self.supplier_id.id,
            'is_automated': True,
            'order_line': [(0, 0, {
                'product_id': self.product_id.id,
                'product_qty': self.suggested_order_qty,
                'price_unit': self.last_purchase_price,
            })]
        }
        
        po = self.env['purchase.order'].create(po_vals)
        
        self.write({
            'state': 'po_created',
            'purchase_order_id': po.id
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'purchase.order',
            'res_id': po.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_bulk_purchase_orders(self):
        """Crear órdenes de compra para múltiples productos (agrupar por proveedor)"""
        if not self:
            raise UserError(_('No hay productos seleccionados.'))
        
        # Agrupar por proveedor
        by_supplier = {}
        for record in self.filtered(lambda r: r.supplier_id and r.suggested_order_qty > 0):
            supplier_id = record.supplier_id.id
            if supplier_id not in by_supplier:
                by_supplier[supplier_id] = []
            by_supplier[supplier_id].append(record)
        
        created_pos = self.env['purchase.order']
        
        for supplier_id, records in by_supplier.items():
            po_lines = []
            for rec in records:
                po_lines.append((0, 0, {
                    'product_id': rec.product_id.id,
                    'product_qty': rec.suggested_order_qty,
                    'price_unit': rec.last_purchase_price,
                }))
            
            po = self.env['purchase.order'].create({
                'partner_id': supplier_id,
                'is_automated': True,
                'order_line': po_lines
            })
            created_pos |= po
            
            # Actualizar estado de los registros
            for rec in records:
                rec.write({
                    'state': 'po_created',
                    'purchase_order_id': po.id
                })
        
        if len(created_pos) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'res_id': created_pos.id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'purchase.order',
                'domain': [('id', 'in', created_pos.ids)],
                'view_mode': 'list,form',
                'target': 'current',
                'name': _('Órdenes de Compra Creadas'),
            }

    def action_ignore(self):
        """Marcar como ignorado"""
        self.write({'state': 'ignored'})

    def action_reset(self):
        """Resetear a pendiente"""
        self.write({
            'state': 'pending',
            'purchase_order_id': False
        })

    def action_refresh_data(self):
        """Refrescar los cálculos"""
        self.write({'last_refresh': fields.Datetime.now()})
        self._compute_stock_metrics()
        self._compute_demand_metrics()
        self._compute_sales_pipeline()
        self._compute_lost_sales_risk()
        self._compute_projections()
        self._compute_recommendation()
        self._compute_priority()

    @api.model
    def action_generate_reorder_commands(self):
        """
        Método Cron: Generar/Actualizar el centro de comando de reorden
        Analiza todos los productos y crea registros para los que necesitan reorden
        """
        _logger.info("=== Iniciando generación de Centro de Comando de Reorden ===")
        
        # Buscar productos almacenables con compra habilitada
        products = self.env['product.product'].search([
            ('is_storable', '=', True),
            ('purchase_ok', '=', True),
            ('active', '=', True)
        ])
        
        _logger.info(f"Analizando {len(products)} productos...")
        
        for product in products:
            # Verificar si ya existe un registro pendiente
            existing = self.search([
                ('product_id', '=', product.id),
                ('state', '=', 'pending')
            ], limit=1)
            
            if existing:
                # Actualizar
                existing.action_refresh_data()
            else:
                # Crear nuevo si cumple criterios de reorden
                # Calcular stock
                total_stock = product.qty_available
                daily_usage = 0
                
                # Calcular consumo diario
                moves = self.env['stock.move'].search([
                    ('product_id', '=', product.id),
                    ('state', '=', 'done'),
                    ('location_dest_id.usage', '=', 'customer'),
                    ('date', '>=', fields.Date.today() - timedelta(days=30))
                ])
                if moves:
                    daily_usage = sum(moves.mapped('quantity')) / 30
                
                # Calcular demanda del pipeline
                pipeline_qty = 0
                quote_lines = self.env['sale.order.line'].search([
                    ('product_id', '=', product.id),
                    ('order_id.state', 'in', ['draft', 'sent', 'sale'])
                ])
                if quote_lines:
                    for line in quote_lines:
                        pipeline_qty += line.product_uom_qty - line.qty_delivered
                
                # Determinar si necesita reorden
                reorder_point = product.reorder_point if hasattr(product, 'reorder_point') else 10
                needs_reorder = (
                    total_stock <= reorder_point or
                    (daily_usage > 0 and total_stock / daily_usage <= 14) or
                    pipeline_qty > total_stock
                )
                
                if needs_reorder:
                    self.create({
                        'product_id': product.id,
                    })
                    _logger.info(f"Creado registro de reorden para: {product.name}")
        
        # Limpiar registros que ya no necesitan reorden
        old_records = self.search([
            ('state', '=', 'pending'),
            ('priority_score', '<', 10),
            ('lost_sales_risk_qty', '<=', 0),
            ('days_until_stockout', '>', 60)
        ])
        if old_records:
            old_records.write({'active': False})
            _logger.info(f"Archivados {len(old_records)} registros que ya no requieren reorden")
        
        _logger.info("=== Completada generación de Centro de Comando de Reorden ===")
        return True


class PIReorderCommandWarehouse(models.Model):
    """Detalle de stock por almacén para el centro de comando"""
    _name = 'pi.reorder.command.warehouse'
    _description = 'Detalle por Almacén del Centro de Comando'
    _order = 'stock_available asc'
    
    command_id = fields.Many2one(
        'pi.reorder.command',
        string='Comando de Reorden',
        ondelete='cascade',
        required=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Almacén',
        required=True
    )
    stock_available = fields.Float(string='Stock Disponible')
    stock_reserved = fields.Float(string='Stock Reservado')
    stock_incoming = fields.Float(string='Stock Entrante')
    stock_outgoing = fields.Float(string='Stock Saliente')
    daily_usage = fields.Float(string='Consumo Diario')
    days_of_stock = fields.Float(
        string='Días de Stock',
        compute='_compute_days_of_stock',
        store=True
    )
    needs_reorder = fields.Boolean(
        string='Necesita Reorden',
        compute='_compute_needs_reorder',
        store=True
    )
    status = fields.Selection([
        ('critical', 'Crítico'),
        ('low', 'Bajo'),
        ('ok', 'OK'),
        ('excess', 'Exceso')
    ], string='Estado', compute='_compute_status', store=True)

    @api.depends('stock_available', 'daily_usage')
    def _compute_days_of_stock(self):
        for record in self:
            if record.daily_usage > 0:
                record.days_of_stock = record.stock_available / record.daily_usage
            else:
                record.days_of_stock = 999

    @api.depends('days_of_stock', 'stock_available')
    def _compute_needs_reorder(self):
        for record in self:
            record.needs_reorder = record.stock_available <= 0 or record.days_of_stock < 14

    @api.depends('stock_available', 'days_of_stock')
    def _compute_status(self):
        for record in self:
            if record.stock_available <= 0:
                record.status = 'critical'
            elif record.days_of_stock < 7:
                record.status = 'low'
            elif record.days_of_stock > 60:
                record.status = 'excess'
            else:
                record.status = 'ok'
