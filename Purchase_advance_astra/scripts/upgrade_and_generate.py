#!/usr/bin/env python3
"""
Script to upgrade Purchase_advance_astra module and generate warehouse intelligence data.
Run this script from Odoo shell or as a scheduled action.
"""

def upgrade_and_generate_data(env):
    """
    Upgrade module and generate warehouse intelligence data
    """
    print("=" * 70)
    print("PASO 1: Actualizando módulo Purchase_advance_astra")
    print("=" * 70)
    
    # Get the module
    module = env['ir.module.module'].search([
        ('name', '=', 'Purchase_advance_astra')
    ], limit=1)
    
    if not module:
        print("❌ ERROR: Módulo 'Purchase_advance_astra' no encontrado!")
        return False
    
    if module.state != 'installed':
        print(f"❌ ERROR: Módulo está en estado '{module.state}', debe estar 'installed'")
        return False
    
    # Upgrade the module
    print(f"✅ Módulo encontrado (estado: {module.state})")
    print("🔄 Iniciando actualización...")
    
    try:
        module.button_immediate_upgrade()
        print("✅ Módulo actualizado exitosamente!")
    except Exception as e:
        print(f"⚠️  Advertencia durante upgrade: {e}")
        print("   Continuando con generación de datos...")
    
    print("\n" + "=" * 70)
    print("PASO 2: Generando datos de inteligencia de almacén")
    print("=" * 70)
    
    # Count products
    products = env['product.template'].search([('type', '=', 'product')])
    warehouses = env['stock.warehouse'].search([])
    
    print(f"📦 Productos almacenables encontrados: {len(products)}")
    print(f"🏭 Almacenes encontrados: {len(warehouses)}")
    
    if not products:
        print("⚠️  No hay productos almacenables. Crea algunos primero.")
        return False
    
    if not warehouses:
        print("⚠️  No hay almacenes configurados. Configura almacenes primero.")
        return False
    
    print("\n🔄 Recalculando inteligencia de stock para todos los productos...")
    
    try:
        # Force recalculation for all products
        for i, product in enumerate(products, 1):
            if i % 10 == 0:
                print(f"   Procesando producto {i}/{len(products)}...")
            
            # Force computation
            product._compute_is_storable()
            product._compute_consumption_stats()
            product._compute_intelligent_stock_levels()
            product._compute_stock_risk()
        
        print(f"✅ {len(products)} productos procesados!")
        
        # Count generated warehouse intelligence records
        intel_records = env['pi.product.warehouse.intelligence'].search([])
        print(f"✅ {len(intel_records)} registros de inteligencia de almacén generados!")
        
    except Exception as e:
        print(f"❌ ERROR durante generación: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n" + "=" * 70)
    print("PASO 3: Generando inteligencia global de almacenes")
    print("=" * 70)
    
    try:
        result = env['warehouse.intelligence'].action_generate_warehouse_intelligence()
        print(f"✅ Inteligencia de almacén generada:")
        print(f"   - Registros creados: {result.get('created', 0)}")
        print(f"   - Registros actualizados: {result.get('updated', 0)}")
    except Exception as e:
        print(f"⚠️  Advertencia: {e}")
        print("   (Esto es opcional, la inteligencia por producto ya fue generada)")
    
    print("\n" + "=" * 70)
    print("✅ PROCESO COMPLETADO EXITOSAMENTE!")
    print("=" * 70)
    print("\nAhora puedes:")
    print("1. Ir a una Orden de Compra")
    print("2. Abrir pestaña '🧠 Inteligencia de Compras'")
    print("3. Ver sección '📊 Análisis por Almacén (Kanban Dashboard)'")
    print("4. O abrir un producto y ver la pestaña '🧠 Inteligencia de Stock'")
    
    return True


# If running from shell, execute directly
if __name__ == '__main__' and 'env' in dir():
    upgrade_and_generate_data(env)
