# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)


def _post_init_hook(env):
    """
    Hook post-instalación: Genera automáticamente TODOS los datos
    para que el usuario no tenga que crear nada manualmente.
    """
    _logger.info("=== Purchase Intelligence: Iniciando generación automática de datos ===")
    
    try:
        # 1. Recalcular inteligencia de stock para TODOS los productos
        _logger.info("1/5 - Calculando inteligencia de stock...")
        products = env['product.template'].search([('type', '=', 'product')])
        products.action_recalculate_all_stock_intelligence()
        
        # 2. Generar optimizaciones de reorden para TODOS los productos
        _logger.info("2/5 - Generando optimizaciones de reorden...")
        env['pi.reorder.optimization'].action_generate_all_optimizations()
        
        # 3. Generar scorecards para TODOS los proveedores
        _logger.info("3/5 - Generando evaluaciones de proveedores...")
        env['pi.supplier.scorecard'].action_generate_all_scorecards()
        
        # 4. Generar pronósticos de demanda
        _logger.info("4/5 - Generando pronósticos de demanda...")
        env['purchase.intelligence.forecast'].action_update_forecasts()
        
        # 5. Calcular KPIs diarios
        _logger.info("5/5 - Calcular KPIs iniciales...")
        env['purchase.intelligence.kpi'].action_calculate_daily_warehouse_kpis()
        
        _logger.info("=== Purchase Intelligence: Generación automática COMPLETADA ===")
        
    except Exception as e:
        _logger.error(f"Error en generación automática: {e}")


def post_init_hook(env):
    """Hook de post-instalación ejecutado después de instalar/actualizar el módulo (Odoo 19+)"""
    _post_init_hook(env)
