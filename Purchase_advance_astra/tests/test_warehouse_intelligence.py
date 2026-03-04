# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo 19 - Purchase Intelligence Module Tests
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

from odoo.tests import common, tagged
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


@tagged('post_install', '-at_install')
class TestWarehouseIntelligence(common.TransactionCase):
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Crear datos de prueba
        cls.warehouse_main = cls.env['stock.warehouse'].create({
            'name': 'Main Warehouse',
            'code': 'WH-MAIN',
            'warehouse_type': 'main_warehouse',
        })
        
        cls.warehouse_secondary = cls.env['stock.warehouse'].create({
            'name': 'Secondary Warehouse',
            'code': 'WH-SEC',
            'warehouse_type': 'secondary_warehouse',
        })
        
        cls.product_a = cls.env['product.template'].create({
            'name': 'Product A',
            'type': 'product',
            'standard_price': 100.0,
            'reorder_point': 50.0,
            'safety_stock': 20.0,
            'abc_classification': 'A',
        })
        
        cls.product_b = cls.env['product.template'].create({
            'name': 'Product B',
            'type': 'product',
            'standard_price': 50.0,
            'reorder_point': 100.0,
            'safety_stock': 30.0,
            'abc_classification': 'B',
        })
        
        cls.supplier = cls.env['res.partner'].create({
            'name': 'Test Supplier',
            'supplier_rank': 1,
        })
        
        # Crear stock inicial
        cls._create_stock(cls.product_a, cls.warehouse_main, 30.0)  # Abajo de reorder point
        cls._create_stock(cls.product_b, cls.warehouse_main, 150.0)  # Arriba de reorder point
        cls._create_stock(cls.product_a, cls.warehouse_secondary, 80.0)  # Arriba de reorder point
        cls._create_stock(cls.product_b, cls.warehouse_secondary, 40.0)  # Abajo de reorder point
    
    def _create_stock(self, product, warehouse, quantity):
        """Crear stock para un producto en un almacén específico"""
        location = warehouse.lot_stock_id
        self.env['stock.quant']._update_available_quantity(
            product.product_variant_id,
            location,
            quantity
        )
    
    def test_warehouse_intelligence_creation(self):
        """Probar creación de inteligencia de almacén"""
        warehouse_intel = self.env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_main.id,
            'date': '2024-01-01',
        })
        
        self.assertEqual(warehouse_intel.warehouse_id, self.warehouse_main)
        self.assertEqual(warehouse_intel.date, '2024-01-01')
        
        # Probar cálculo de métricas
        warehouse_intel._compute_metrics()
        
        self.assertGreaterEqual(warehouse_intel.total_products, 0)
        self.assertGreaterEqual(warehouse_intel.critical_products, 0)
    
    def test_warehouse_specific_stock_calculation(self):
        """Probar cálculo de stock específico por almacén"""
        # Establecer contexto de almacén
        product = self.product_a.with_context(warehouse_id=self.warehouse_main.id)
        
        # Recalcular inteligencia de stock
        product.action_recalculate_all_stock_intelligence()
        
        # Verificar que se use el stock del almacén específico
        warehouse_stock = product._get_warehouse_stock(product)
        self.assertIsNotNone(warehouse_stock)
        self.assertEqual(warehouse_stock, 30.0)  # Stock creado en setUp
    
    def test_warehouse_reorder_suggestions(self):
        """Probar sugerencias de reorden específicas por almacén"""
        # Generar órdenes automatizadas para almacén principal
        orders = self.env['pi.automated.order'].generate_warehouse_automated_orders(
            warehouse_id=self.warehouse_main.id
        )
        
        self.assertGreater(len(orders), 0)
        
        # Verificar que las órdenes sean para el almacén correcto
        for order in orders:
            self.assertEqual(order.warehouse_id, self.warehouse_main)
            self.assertTrue(order.is_warehouse_specific)
            
            # Verificar cálculos específicos del almacén
            order._compute_warehouse_metrics()
            self.assertGreater(order.warehouse_priority_score, 0)
    
    def test_warehouse_kpi_calculation(self):
        """Probar cálculo de KPIs específicos por almacén"""
        # Calcular KPIs para almacén principal
        kpi_result = self.env['purchase.intelligence.kpi'].calculate_warehouse_kpis(
            warehouse_id=self.warehouse_main.id
        )
        
        self.assertIn('kpi_results', kpi_result)
        self.assertIn('comparison_data', kpi_result)
        
        # Verificar estructura de KPIs
        kpi_data = kpi_result['kpi_results'][0]
        self.assertIn('financial', kpi_data)
        self.assertIn('operational', kpi_data)
        self.assertIn('inventory', kpi_data)
        self.assertIn('supplier', kpi_data)
        
        # Verificar KPIs financieros
        financial_kpis = kpi_data['financial']
        self.assertIn('total_stock_value', financial_kpis)
        self.assertIn('monthly_spend', financial_kpis)
        self.assertIn('turnover', financial_kpis)
    
    def test_warehouse_comparison_analytics(self):
        """Probar análisis de comparación entre almacenes"""
        # Crear inteligencia para ambos almacenes
        intel_main = self.env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_main.id,
            'date': '2024-01-01',
        })
        intel_main._compute_metrics()
        
        intel_sec = self.env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_secondary.id,
            'date': '2024-01-01',
        })
        intel_sec._compute_metrics()
        
        # Probar método de comparación
        comparison = intel_main.get_warehouse_comparison_data()
        
        self.assertIn('comparison_data', comparison)
        self.assertIn('best_warehouse', comparison)
        self.assertIn('worst_warehouse', comparison)
        
        # Verificar que ambos almacenes estén en la comparación
        comparison_data = comparison['comparison_data']
        warehouse_names = [w['warehouse_name'] for w in comparison_data]
        self.assertIn(self.warehouse_main.name, warehouse_names)
        self.assertIn(self.warehouse_secondary.name, warehouse_names)
    
    def test_warehouse_urgency_calculation(self):
        """Probar cálculo de urgencia específica por almacén"""
        # Crear orden automatizada para producto con bajo stock
        order = self.env['pi.automated.order'].create({
            'product_id': self.product_a.id,
            'warehouse_id': self.warehouse_main.id,
            'suggested_quantity': 100.0,
        })
        
        # Calcular métricas específicas del almacén
        order._compute_warehouse_metrics()
        
        # Verificar nivel de urgencia (debería ser crítico o alto)
        self.assertIn(order.warehouse_urgency_level, ['critical', 'high'])
        
        # Verificar score de prioridad
        self.assertGreater(order.warehouse_priority_score, 50)
    
    def test_warehouse_adjustment_factors(self):
        """Probar factores de ajuste por tipo de almacén"""
        # Crear almacenes de diferentes tipos
        warehouse_virtual = self.env['stock.warehouse'].create({
            'name': 'Virtual Warehouse',
            'code': 'WH-VIRT',
            'warehouse_type': 'virtual_warehouse',
        })
        
        # Crear orden para cada tipo de almacén
        order_main = self.env['pi.automated.order'].create({
            'product_id': self.product_a.id,
            'warehouse_id': self.warehouse_main.id,
        })
        
        order_virtual = self.env['pi.automated.order'].create({
            'product_id': self.product_a.id,
            'warehouse_id': warehouse_virtual.id,
        })
        
        # Calcular factores de ajuste
        factor_main = order_main._get_warehouse_adjustment_factor()
        factor_virtual = order_virtual._get_warehouse_adjustment_factor()
        
        # Verificar que el almacén principal tenga mayor factor
        self.assertGreater(factor_main, factor_virtual)
        self.assertEqual(factor_virtual, 0.0)  # Almacén virtual no mantiene stock
    
    def test_warehouse_dashboard_data(self):
        """Probar generación de datos para dashboard"""
        # Generar inteligencia para el almacén
        intel = self.env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_main.id,
            'date': '2024-01-01',
        })
        intel._compute_metrics()
        
        # Obtener datos del dashboard
        dashboard_data = intel.get_warehouse_dashboard_data()
        
        self.assertIn('warehouse_info', dashboard_data)
        self.assertIn('metrics', dashboard_data)
        self.assertIn('abc_analysis', dashboard_data)
        self.assertIn('supplier_metrics', dashboard_data)
        
        # Verificar métricas principales
        metrics = dashboard_data['metrics']
        self.assertIn('total_products', metrics)
        self.assertIn('critical_products', metrics)
        self.assertIn('stock_availability', metrics)
    
    def test_warehouse_context_propagation(self):
        """Probar propagación de contexto de almacén"""
        # Establecer contexto de almacén
        product = self.product_a.with_context(warehouse_id=self.warehouse_main.id)
        
        # Verificar que el contexto se use en los cálculos
        self.assertEqual(product.env.context.get('warehouse_id'), self.warehouse_main.id)
        
        # Probar cálculo con contexto
        stock_level = product._get_warehouse_stock(product)
        self.assertIsNotNone(stock_level)
        
        # Probar sin contexto
        product_no_context = self.product_a.with_context(warehouse_id=None)
        stock_level_no_context = product_no_context._get_warehouse_stock(product_no_context)
        self.assertIsNone(stock_level_no_context)
    
    def test_warehouse_security_rules(self):
        """Probar reglas de seguridad por almacén"""
        # Crear usuario con acceso a un solo almacén
        user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'testuser@example.com',
            'password': 'test123',
            'warehouse_ids': [(4, self.warehouse_main.id)],
        })
        
        # Asignar grupo de usuario de inteligencia
        user.groups_id += self.env.ref('purchase_advance_astra.group_warehouse_intelligence_user')
        
        # Cambiar a este usuario
        user_env = self.env(user=user)
        
        # Verificar que solo pueda ver inteligencia de su almacén
        intel_main = user_env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_main.id,
            'date': '2024-01-01',
        })
        
        # Intentar crear inteligencia para otro almacén (debería fallar)
        with self.assertRaises(Exception):
            intel_sec = user_env['warehouse.intelligence'].create({
                'warehouse_id': self.warehouse_secondary.id,
                'date': '2024-01-01',
            })
    
    def test_warehouse_report_generation(self):
        """Probar generación de reportes por almacén"""
        # Crear inteligencia para el almacén
        intel = self.env['warehouse.intelligence'].create({
            'warehouse_id': self.warehouse_main.id,
            'date': '2024-01-01',
        })
        intel._compute_metrics()
        
        # Probar generación de reporte
        report_action = self.env.ref('purchase_advance_astra.report_warehouse_intelligence').report_action(intel)
        
        self.assertEqual(report_action['report_name'], 'purchase_advance_astra.report_warehouse_intelligence')
        self.assertIn(intel.id, report_action.get('active_ids', []))
    
    def test_warehouse_automated_order_creation(self):
        """Probar creación automática de órdenes por almacén"""
        # Crear configuración de proveedor para el producto
        self.env['product.supplierinfo'].create({
            'product_tmpl_id': self.product_a.id,
            'partner_id': self.supplier.id,
            'price': 100.0,
            'min_qty': 1.0,
        })
        
        # Generar órdenes automatizadas
        orders = self.env['pi.automated.order'].generate_warehouse_automated_orders()
        
        self.assertGreater(len(orders), 0)
        
        # Verificar que las órdenes tengan todos los campos requeridos
        for order in orders:
            self.assertTrue(order.warehouse_id)
            self.assertTrue(order.product_id)
            self.assertGreater(order.suggested_quantity, 0)
            self.assertTrue(order.is_warehouse_specific)
    
    def test_warehouse_daily_usage_calculation(self):
        """Probar cálculo de uso diario por almacén"""
        # Crear movimientos de stock de prueba
        self._create_stock_movement(self.product_a, self.warehouse_main, 10.0)
        
        # Calcular uso diario
        daily_usage = self.env['pi.automated.order']._get_product_daily_usage_warehouse(
            self.product_a, self.warehouse_main
        )
        
        self.assertGreaterEqual(daily_usage, 0)
    
    def _create_stock_movement(self, product, warehouse, quantity):
        """Crear movimiento de stock de prueba"""
        # Crear transferencia de salida
        picking = self.env['stock.picking'].create({
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        
        move = self.env['stock.move'].create({
            'name': 'Test Move',
            'product_id': product.product_variant_id.id,
            'product_uom_qty': quantity,
            'picking_id': picking.id,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
        })
        
        move._action_confirm()
        move._action_assign()
        move.quantity_done = quantity
        move._action_done()


@tagged('post_install', '-at_install')
class TestWarehouseIntegration(common.TransactionCase):
    """Tests de integración para funcionalidades multi-almacén"""
    
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        
        # Configurar datos de prueba más complejos
        cls.warehouses = cls.env['stock.warehouse'].search([], limit=3)
        cls.products = cls.env['product.template'].search([('type', '=', 'product')], limit=5)
    
    def test_multi_warehouse_intelligence_sync(self):
        """Probar sincronización de inteligencia entre almacenes"""
        # Generar inteligencia para todos los almacenes
        result = self.env['warehouse.intelligence'].action_generate_warehouse_intelligence()
        
        self.assertTrue(result)
        
        # Verificar que se haya generado inteligencia para cada almacén
        intel_records = self.env['warehouse.intelligence'].search([
            ('date', '=', fields.Date.today())
        ])
        
        self.assertEqual(len(intel_records), len(self.warehouses))
    
    def test_warehouse_performance_ranking(self):
        """Probar sistema de ranking de rendimiento de almacenes"""
        # Crear inteligencia para todos los almacenes
        for warehouse in self.warehouses:
            intel = self.env['warehouse.intelligence'].create({
                'warehouse_id': warehouse.id,
                'date': fields.Date.today(),
            })
            intel._compute_metrics()
        
        # Obtener datos de comparación
        intel_first = self.env['warehouse.intelligence'].search([], limit=1)
        comparison = intel_first.get_warehouse_comparison_data()
        
        self.assertIn('comparison_data', comparison)
        self.assertEqual(len(comparison['comparison_data']), len(self.warehouses))
        
        # Verificar que haya rankings
        for warehouse_data in comparison['comparison_data']:
            self.assertIn('performance_rank', warehouse_data)
            self.assertIn('efficiency_score', warehouse_data)
    
    def test_warehouse_kpi_historical_tracking(self):
        """Probar seguimiento histórico de KPIs por almacén"""
        warehouse = self.warehouses[0]
        
        # Generar KPIs para diferentes fechas
        dates = ['2024-01-01', '2024-01-02', '2024-01-03']
        
        for date in dates:
            self.env['purchase.intelligence.kpi'].calculate_warehouse_kpis(
                warehouse_id=warehouse.id
            )
        
        # Verificar que se hayan creado registros históricos
        kpi_records = self.env['purchase.intelligence.kpi'].search([
            ('warehouse_id', '=', warehouse.id)
        ])
        
        self.assertGreater(len(kpi_records), 0)
        
        # Verificar que cada KPI tenga el almacén correcto
        for kpi in kpi_records:
            self.assertEqual(kpi.warehouse_id, warehouse)
            self.assertTrue(kpi.is_warehouse_specific)