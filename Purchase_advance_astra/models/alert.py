# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class PurchaseIntelligenceAlert(models.Model):
    _name = 'purchase.intelligence.alert'
    _description = 'Configuración de Alertas de Compras'

    name = fields.Char(string='Nombre de Alerta', required=True)
    model_id = fields.Many2one('ir.model', string='Modelo', required=True, ondelete='cascade')
    active = fields.Boolean(default=True)

    trigger_condition = fields.Selection([
        ('stock_low', 'Stock Bajo'),
        ('price_spike', 'Pico de Precio'),
        ('supplier_risk', 'Riesgo de Proveedor'),
        ('contract_expiry', 'Vencimiento de Contrato'),
        ('quality_failure', 'Fallo de Calidad'),
        # Nuevas condiciones de alerta
        ('stock_low_pending_sales', 'Stock Bajo + Ventas Pendientes'),
        ('frequent_stockout', 'Producto con Desabasto Frecuente'),
        ('warehouse_imbalance', 'Desbalance entre Almacenes'),
        ('lost_sales_risk', 'Riesgo Alto de Ventas Perdidas'),
    ], string='Condición de Disparo')

    threshold_value = fields.Float(string='Valor Umbral')
    priority = fields.Selection([
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', 'Crítico')
    ], string='Prioridad', default='medium')

    action_type = fields.Selection([
        ('email', 'Enviar Correo'),
        ('activity', 'Programar Actividad'),
        ('notification', 'Notificación del Sistema')
    ], string='Tipo de Acción', default='activity')

    user_ids = fields.Many2many('res.users', string='Notificar Usuarios')
    
    # Campos adicionales para compatibilidad con dashboard
    message = fields.Text(string='Mensaje de Alerta')
    date = fields.Date(string='Fecha', default=fields.Date.context_today)
    status = fields.Selection([
        ('active', 'Activa'),
        ('resolved', 'Resuelta'),
        ('dismissed', 'Descartada')
    ], string='Estado', default='active')

    @api.model
    def check_and_generate_alerts(self):
        """
        Método Cron: Verificar condiciones y generar alertas
        Ahora incluye alertas para riesgo de ventas perdidas y desbalance de almacenes
        """
        today = fields.Date.context_today(self)
        AlertLog = self.env['pi.alert.log']
        
        _logger.info("=== Iniciando verificación de alertas de compras ===")
        
        # 1. Verificar productos con stock bajo
        low_stock_products = self.env['product.product'].search([
            ('qty_available', '<', 10),
            ('is_storable', '=', True),
            ('purchase_ok', '=', True)
        ])
        
        for product in low_stock_products:
            existing = AlertLog.search([
                ('res_model', '=', 'product.product'),
                ('res_id', '=', product.id),
                ('state', '=', 'new'),
                ('name', 'ilike', 'Stock Crítico')
            ], limit=1)
            
            if not existing:
                AlertLog.create({
                    'name': f'Stock Crítico: {product.name}',
                    'severity': 'critical',
                    'message': f'El producto {product.name} tiene solo {product.qty_available} unidades en stock.',
                    'res_model': 'product.product',
                    'res_id': product.id,
                })
        
        # 2. Verificar contratos por vencer
        try:
            expiring_contracts = self.env['pi.contract.performance'].search([
                ('end_date', '<=', today + timedelta(days=30)),
                ('end_date', '>=', today),
                ('state', '=', 'active')
            ])
            
            for contract in expiring_contracts:
                days_remaining = (contract.end_date - today).days
                severity = 'critical' if days_remaining < 7 else 'high' if days_remaining < 15 else 'medium'
                
                existing = AlertLog.search([
                    ('res_model', '=', 'pi.contract.performance'),
                    ('res_id', '=', contract.id),
                    ('state', '=', 'new')
                ], limit=1)
                
                if not existing:
                    AlertLog.create({
                        'name': f'Contrato por Vencer: {contract.name}',
                        'severity': severity,
                        'message': f'El contrato {contract.name} vence en {days_remaining} días.',
                        'res_model': 'pi.contract.performance',
                        'res_id': contract.id,
                    })
        except Exception as e:
            _logger.warning(f"Error al verificar contratos: {e}")
        
        # 3. Verificar órdenes pendientes de aprobación
        pending_orders = self.env['purchase.order'].search([
            ('state', '=', 'to approve'),
            ('create_date', '<', fields.Datetime.now() - timedelta(days=2))
        ])
        
        for po in pending_orders:
            existing = AlertLog.search([
                ('res_model', '=', 'purchase.order'),
                ('res_id', '=', po.id),
                ('state', '=', 'new')
            ], limit=1)
            
            if not existing:
                AlertLog.create({
                    'name': f'Orden Pendiente: {po.name}',
                    'severity': 'high',
                    'message': f'La orden {po.name} está pendiente de aprobación hace más de 2 días.',
                    'res_model': 'purchase.order',
                    'res_id': po.id,
                })
        
        # 4. NUEVO: Verificar productos con stock bajo Y ventas pendientes (riesgo de ventas perdidas)
        self._check_lost_sales_risk_alerts(AlertLog, today)
        
        # 5. NUEVO: Verificar desbalance entre almacenes
        self._check_warehouse_imbalance_alerts(AlertLog, today)
        
        # 6. NUEVO: Verificar productos con desabasto frecuente
        self._check_frequent_stockout_alerts(AlertLog, today)
        
        _logger.info("=== Completada verificación de alertas de compras ===")
        return True

    def _check_lost_sales_risk_alerts(self, AlertLog, today):
        """Verificar productos donde el stock no puede cubrir la demanda del pipeline"""
        _logger.info("Verificando alertas de riesgo de ventas perdidas...")
        
        # Buscar productos almacenables con ventas
        products = self.env['product.product'].search([
            ('is_storable', '=', True),
            ('purchase_ok', '=', True),
            ('qty_available', '>', 0)
        ])
        
        for product in products:
            # Calcular demanda del pipeline
            quote_lines = self.env['sale.order.line'].search([
                ('product_id', '=', product.id),
                ('order_id.state', 'in', ['draft', 'sent', 'sale'])
            ])
            
            total_pipeline = 0
            for line in quote_lines:
                if line.order_id.state in ['draft', 'sent']:
                    total_pipeline += line.product_uom_qty
                else:
                    # Órdenes confirmadas: solo contar lo no entregado
                    total_pipeline += max(0, line.product_uom_qty - line.qty_delivered)
            
            # Si la demanda del pipeline supera el stock disponible
            shortage = total_pipeline - product.qty_available
            if shortage > 0:
                # Calcular el valor en riesgo
                risk_amount = shortage * (product.list_price or product.standard_price)
                
                # Determinar severidad
                if risk_amount > 10000:
                    severity = 'critical'
                elif risk_amount > 5000:
                    severity = 'high'
                elif risk_amount > 1000:
                    severity = 'medium'
                else:
                    continue  # No alertar para montos pequeños
                
                existing = AlertLog.search([
                    ('res_model', '=', 'product.product'),
                    ('res_id', '=', product.id),
                    ('state', '=', 'new'),
                    ('name', 'ilike', 'Riesgo de Ventas Perdidas')
                ], limit=1)
                
                if not existing:
                    AlertLog.create({
                        'name': f'🚨 Riesgo de Ventas Perdidas: {product.name}',
                        'severity': severity,
                        'message': f'''El producto "{product.name}" tiene {product.qty_available:.0f} unidades en stock 
pero hay {total_pipeline:.0f} unidades en el pipeline de ventas.
Faltante: {shortage:.0f} unidades
Valor en riesgo: ${risk_amount:,.2f}
Se recomienda generar orden de compra urgente.''',
                        'res_model': 'product.product',
                        'res_id': product.id,
                    })
                    _logger.info(f"Alerta creada para {product.name} - Faltante: {shortage}")

    def _check_warehouse_imbalance_alerts(self, AlertLog, today):
        """Verificar productos con desbalance significativo entre almacenes"""
        _logger.info("Verificando alertas de desbalance entre almacenes...")
        
        try:
            warehouses = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)])
            
            if len(warehouses) < 2:
                return  # Se necesitan al menos 2 almacenes para comparar
            
            products = self.env['product.product'].search([
                ('is_storable', '=', True),
                ('purchase_ok', '=', True)
            ], limit=500)  # Limitar para rendimiento
            
            for product in products:
                stock_by_wh = {}
                for wh in warehouses:
                    quants = self.env['stock.quant'].search([
                        ('product_id', '=', product.id),
                        ('location_id', 'child_of', wh.lot_stock_id.id)
                    ])
                    stock_by_wh[wh.id] = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
                
                if not stock_by_wh:
                    continue
                
                max_stock = max(stock_by_wh.values())
                min_stock = min(stock_by_wh.values())
                
                # Detectar desbalance: un almacén tiene >30 días de stock mientras otro tiene <7
                # Simplificado: detectar si hay gran diferencia y un almacén está en 0
                if max_stock > 100 and min_stock <= 0:
                    wh_max = [wh for wh in warehouses if stock_by_wh.get(wh.id) == max_stock]
                    wh_min = [wh for wh in warehouses if stock_by_wh.get(wh.id) == min_stock]
                    
                    if wh_max and wh_min:
                        existing = AlertLog.search([
                            ('res_model', '=', 'product.product'),
                            ('res_id', '=', product.id),
                            ('state', '=', 'new'),
                            ('name', 'ilike', 'Desbalance')
                        ], limit=1)
                        
                        if not existing:
                            AlertLog.create({
                                'name': f'Desbalance de Stock: {product.name}',
                                'severity': 'medium',
                                'message': f'''El producto "{product.name}" tiene desbalance entre almacenes:
{wh_max[0].name}: {max_stock:.0f} unidades
{wh_min[0].name}: {min_stock:.0f} unidades
Se recomienda transferencia interna.''',
                                'res_model': 'product.product',
                                'res_id': product.id,
                            })
        except Exception as e:
            _logger.warning(f"Error al verificar desbalance de almacenes: {e}")

    def _check_frequent_stockout_alerts(self, AlertLog, today):
        """Verificar productos que han tenido desabasto frecuente"""
        _logger.info("Verificando alertas de desabasto frecuente...")
        
        try:
            # Buscar movimientos de stock que indiquen desabasto (backorders, etc.)
            ninety_days_ago = today - timedelta(days=90)
            
            # Buscar productos con múltiples alertas de stock bajo en los últimos 90 días
            frequent_alerts = self.env['pi.alert.log'].read_group(
                [
                    ('create_date', '>=', ninety_days_ago),
                    ('res_model', '=', 'product.product'),
                    ('name', 'ilike', 'Stock')
                ],
                ['res_id'],
                ['res_id']
            )
            
            for alert_group in frequent_alerts:
                if alert_group.get('res_id_count', 0) >= 3:
                    product_id = alert_group.get('res_id')
                    product = self.env['product.product'].browse(product_id)
                    
                    if product.exists():
                        existing = AlertLog.search([
                            ('res_model', '=', 'product.product'),
                            ('res_id', '=', product_id),
                            ('state', '=', 'new'),
                            ('name', 'ilike', 'Desabasto Frecuente')
                        ], limit=1)
                        
                        if not existing:
                            AlertLog.create({
                                'name': f'Desabasto Frecuente: {product.name}',
                                'severity': 'high',
                                'message': f'''El producto "{product.name}" ha tenido {alert_group['res_id_count']} alertas de stock en los últimos 90 días.
Se recomienda revisar:
- Punto de reorden (ROP)
- Stock de seguridad
- Lead time del proveedor
- Demanda estacional''',
                                'res_model': 'product.product',
                                'res_id': product_id,
                            })
        except Exception as e:
            _logger.warning(f"Error al verificar desabasto frecuente: {e}")


class PIAlertLog(models.Model):
    _name = 'pi.alert.log'
    _description = 'Registro de Alertas'
    _order = 'create_date desc'

    name = fields.Char(string='Título de Alerta', required=True)
    alert_config_id = fields.Many2one('purchase.intelligence.alert', string='Configuración de Alerta')
    severity = fields.Selection([
        ('low', 'Bajo'),
        ('medium', 'Medio'),
        ('high', 'Alto'),
        ('critical', 'Crítico')
    ], string='Severidad')
    message = fields.Text(string='Mensaje')
    res_model = fields.Char(string='Modelo Relacionado')
    res_id = fields.Integer(string='ID Relacionado')
    state = fields.Selection([
        ('new', 'Nuevo'),
        ('acknowledged', 'Reconocido'),
        ('resolved', 'Resuelto')
    ], default='new')

    def action_resolve(self):
        self.write({'state': 'resolved'})
    
    def action_acknowledge(self):
        self.write({'state': 'acknowledged'})
