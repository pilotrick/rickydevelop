/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class WarehouseDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            warehouses: [],
            selectedWarehouse: null,
            warehouseData: {},
            comparisonData: {},
            loading: true,
            lastUpdate: null,
            availableWarehouses: [],
        });

        onWillStart(async () => {
            await this.loadWarehouses();
            await this.loadWarehouseData();
        });
    }

    async loadWarehouses() {
        try {
            // Cargar todos los almacenes disponibles
            const warehouses = await this.orm.searchRead(
                "stock.warehouse",
                [],
                ["id", "name", "warehouse_type"],
                { limit: 20 }
            );

            this.state.warehouses = warehouses;
            this.state.availableWarehouses = warehouses;

            // Seleccionar el primer almacén por defecto
            if (warehouses.length > 0 && !this.state.selectedWarehouse) {
                this.state.selectedWarehouse = warehouses[0].id;
                await this.loadWarehouseData();
            }

        } catch (error) {
            console.error("Error loading warehouses:", error);
            this.notification.add("Error al cargar almacenes", { type: "danger" });
        }
    }

    async loadWarehouseData() {
        if (!this.state.selectedWarehouse) {
            this.state.warehouseData = {};
            return;
        }

        try {
            this.state.loading = true;

            // Cargar datos específicos del almacén seleccionado
            const warehouseData = await this.orm.call(
                "warehouse.intelligence",
                "get_warehouse_dashboard_data",
                [this.state.selectedWarehouse]
            );

            // Cargar datos de comparación
            const comparisonData = await this.orm.call(
                "warehouse.intelligence",
                "get_warehouse_comparison_data",
                []
            );

            this.state.warehouseData = warehouseData;
            this.state.comparisonData = comparisonData;
            this.state.lastUpdate = new Date().toLocaleString('es-ES');
            this.state.loading = false;

        } catch (error) {
            console.error("Error loading warehouse data:", error);
            this.notification.add("Error al cargar datos del almacén", { type: "danger" });
            this.state.loading = false;
        }
    }

    async onWarehouseChange(event) {
        const warehouseId = parseInt(event.target.value);
        this.state.selectedWarehouse = warehouseId;
        await this.loadWarehouseData();
    }

    async refreshData() {
        await this.loadWarehouseData();
        this.notification.add("Datos actualizados", { type: "success" });
    }

    async generateWarehouseIntelligence() {
        try {
            this.state.loading = true;
            this.notification.add("Generando inteligencia por almacén...", { type: "info" });

            await this.orm.call(
                "warehouse.intelligence",
                "action_generate_warehouse_intelligence",
                []
            );

            await this.loadWarehouseData();
            this.notification.add("✅ Inteligencia generada exitosamente", { type: "success" });

        } catch (error) {
            console.error("Error generating warehouse intelligence:", error);
            this.notification.add("Error al generar inteligencia", { type: "danger" });
        } finally {
            this.state.loading = false;
        }
    }

    openWarehouseComparison() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Comparación de Almacenes",
            res_model: "warehouse.intelligence",
            view_mode: "tree",
            views: [[false, "tree"], [false, "form"]],
            target: "current",
        });
    }

    openCriticalProducts() {
        if (!this.state.selectedWarehouse) return;

        // Abrir productos críticos con contexto de almacén
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Productos Críticos por Almacén",
            res_model: "product.template",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["type", "=", "product"],
                ["stockout_risk", "in", ["critical", "high"]]
            ],
            context: {
                warehouse_id: this.state.selectedWarehouse
            },
            target: "current",
        });
    }

    openReorderSuggestions() {
        if (!this.state.selectedWarehouse) return;

        // Abrir sugerencias de reorden con contexto de almacén
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Sugerencias de Reorden por Almacén",
            res_model: "product.template",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["type", "=", "product"],
                ["needs_reorder", "=", true]
            ],
            context: {
                warehouse_id: this.state.selectedWarehouse
            },
            target: "current",
        });
    }

    openLowStockProducts() {
        if (!this.state.selectedWarehouse) return;

        // Abrir productos con stock bajo con contexto de almacén
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Productos con Stock Bajo por Almacén",
            res_model: "product.template",
            views: [[false, "list"], [false, "form"]],
            domain: [
                ["type", "=", "product"],
                ["days_of_stock", "<", 7],
                ["days_of_stock", ">", 0]
            ],
            context: {
                warehouse_id: this.state.selectedWarehouse
            },
            target: "current",
        });
    }

    formatNumber(value) {
        if (value === null || value === undefined) return '0';
        if (value >= 1000000) {
            return (value / 1000000).toFixed(1) + 'M';
        } else if (value >= 1000) {
            return (value / 1000).toFixed(1) + 'K';
        }
        return value.toLocaleString('es-ES', { maximumFractionDigits: 0 });
    }

    formatDecimal(value) {
        if (value === null || value === undefined) return '0';
        return value.toLocaleString('es-ES', { maximumFractionDigits: 1 });
    }

    formatCurrency(value) {
        if (value === null || value === undefined) return '$0';
        return new Intl.NumberFormat('es-DO', {
            style: 'currency',
            currency: 'DOP'
        }).format(value);
    }

    getWarehouseTypeIcon(warehouseType) {
        const icons = {
            'main_warehouse': '🏢',
            'secondary_warehouse': '🏪',
            'regional_warehouse': '🏬',
            'virtual_warehouse': '☁️',
        };
        return icons[warehouseType] || '🏢';
    }

    getPerformanceClass(rank) {
        if (rank === 1) return 'success';
        if (rank <= 3) return 'warning';
        return 'danger';
    }

    getAvailabilityClass(availability) {
        if (availability >= 95) return 'success';
        if (availability >= 85) return 'warning';
        return 'danger';
    }

    // Template principal
    static template = "purchase_intelligence.WarehouseDashboard";
}

WarehouseDashboard.template = `
<div class="o_dashboard">
    <!-- Selector de Almacén -->
    <div class="o_dashboard_header">
        <div class="o_dashboard_header_left">
            <h2>📊 Inteligencia por Almacén</h2>
            <div class="o_form_label">
                <label for="warehouse_selector">Seleccionar Almacén:</label>
                <select id="warehouse_selector" t-model="selectedWarehouse" t-on-change="onWarehouseChange">
                    <option t-foreach="warehouse in availableWarehouses" 
                            t-att-value="warehouse.id" 
                            t-esc-selected="selectedWarehouse === warehouse.id">
                        <t t-esc="getWarehouseTypeIcon(warehouse.warehouse_type) + ' ' + warehouse.name"/>
                    </option>
                </select>
            </div>
        </div>
        <div class="o_dashboard_header_right">
            <button class="btn btn-primary" t-on-click="refreshData" t-att-disabled="loading">
                🔄 Actualizar
            </button>
            <button class="btn btn-secondary" t-on-click="generateWarehouseIntelligence" t-att-disabled="loading">
                🧠 Generar Inteligencia
            </button>
            <button class="btn btn-info" t-on-click="openWarehouseComparison">
                📊 Comparación
            </button>
        </div>
    </div>

    <!-- Datos del Almacén Seleccionado -->
    <div t-if="warehouseData.warehouse_info" class="o_dashboard_content">
        <div class="o_dashboard_section">
            <h3>📋 <t t-esc="warehouseData.warehouse_info.name"/> - Métricas Principales</h3>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_primary">
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.metrics.total_products or 0"/>
                        </div>
                        <div class="o_stat_label">Total Productos</div>
                    </div>
                </div>
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_warning" t-att-class="'o_stat_' + getPerformanceClass(warehouseData.metrics.performance_rank)">
                        <div class="o_stat_value">
                            #<t t-esc="warehouseData.metrics.performance_rank or 0"/>
                        </div>
                        <div class="o_stat_label">Rank Rendimiento</div>
                    </div>
                </div>
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_success" t-att-class="'o_stat_' + getAvailabilityClass(warehouseData.metrics.stock_availability)">
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.metrics.stock_availability or 0"/>%
                        </div>
                        <div class="o_stat_label">Disponibilidad</div>
                    </div>
                </div>
            </div>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_info">
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.metrics.critical_products or 0"/>
                        </div>
                        <div class="o_stat_label">Productos Críticos</div>
                    </div>
                </div>
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_danger">
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.metrics.products_need_reorder or 0"/>
                        </div>
                        <div class="o_stat_label">Necesitan Reorden</div>
                    </div>
                </div>
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_warning">
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.metrics.low_stock_products or 0"/>
                        </div>
                        <div class="o_stat_label">Stock Bajo</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Análisis de Inventario -->
        <div class="o_dashboard_section">
            <h3>📦 Análisis de Inventario</h3>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col">
                    <h4>Valores Monetarios</h4>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Valor Total Stock:</div>
                        <div class="o_stat_value"><t t-esc="formatCurrency(warehouseData.metrics.total_stock_value)"/></div>
                    </div>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Valor Órdenes Pendientes:</div>
                        <div class="o_stat_value"><t t-esc="formatCurrency(warehouseData.metrics.pending_order_value)"/></div>
                    </div>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Gasto Mensual:</div>
                        <div class="o_stat_value"><t t-esc="formatCurrency(warehouseData.metrics.monthly_spend)"/></div>
                    </div>
                </div>
                </div>
                
                <div class="o_dashboard_col">
                    <h4>KPIs de Inventario</h4>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Rotación:</div>
                        <div class="o_stat_value"><t t-esc="formatDecimal(warehouseData.metrics.stock_turnover)"/>x</div>
                    </div>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Días Inventario:</div>
                        <div class="o_stat_value"><t t-esc="formatDecimal(warehouseData.metrics.days_of_inventory)"/></div>
                    </div>
                    <div class="o_stat_box">
                        <div class="o_stat_label">Tasa Rotura:</div>
                        <div class="o_stat_value"><t t-esc="formatDecimal(warehouseData.metrics.stockout_rate)"/>%</div>
                    </div>
                </div>
                </div>
            </div>
        </div>

        <!-- Análisis ABC -->
        <div class="o_dashboard_section">
            <h3>📊 Análisis ABC</h3>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col_6">
                    <div class="o_stat_box o_stat_success">
                        <div class="o_stat_label">Clase A</div>
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.abc_analysis.a_count or 0"/> productos<br/>
                            <t t-esc="formatCurrency(warehouseData.abc_analysis.a_value)"/>
                        </div>
                    </div>
                </div>
                <div class="o_dashboard_col_6">
                    <div class="o_stat_box o_stat_warning">
                        <div class="o_stat_label">Clase B</div>
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.abc_analysis.b_count or 0"/> productos<br/>
                            <t t-esc="formatCurrency(warehouseData.abc_analysis.b_value)"/>
                        </div>
                    </div>
                </div>
                <div class="o_dashboard_col_6">
                    <div class="o_stat_box o_stat_info">
                        <div class="o_stat_label">Clase C</div>
                        <div class="o_stat_value">
                            <t t-esc="warehouseData.abc_analysis.c_count or 0"/> productos<br/>
                            <t t-esc="formatCurrency(warehouseData.abc_analysis.c_value)"/>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Métricas de Proveedores -->
        <div class="o_dashboard_section">
            <h3>🚚 Métricas de Proveedores</h3>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_info">
                        <div class="o_stat_label">Proveedores Activos</div>
                        <div class="o_stat_value"><t t-esc="warehouseData.supplier_metrics.active_suppliers or 0"/></div>
                    </div>
                    <div class="o_stat_box o_stat_success">
                        <div class="o_stat_label">Tasa Entrega a Tiempo</div>
                        <div class="o_stat_value"><t t-esc="formatDecimal(warehouseData.supplier_metrics.on_time_delivery_rate)"/>%</div>
                    </div>
                </div>
                <div class="o_dashboard_col">
                    <div class="o_stat_box o_stat_warning">
                        <div class="o_stat_label">Tiempo Promedio Entrega</div>
                        <div class="o_stat_value"><t t-esc="formatDecimal(warehouseData.supplier_metrics.avg_delivery_time)"/> días</div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Alertas -->
        <div t-if="warehouseData.alerts.alert_count > 0" class="o_dashboard_section">
            <h3>⚠️ Alertas</h3>
            
            <div class="o_alert_box o_alert_danger">
                <div class="o_alert_title">
                    <t t-esc="warehouseData.alerts.alert_count"/> Alertas Activas
                </div>
                <div class="o_alert_content">
                    <t t-raw="warehouseData.alerts.critical_alerts"/>
                </div>
            </div>
        </div>

        <!-- Acciones Rápidas -->
        <div class="o_dashboard_section">
            <h3>⚡ Acciones Rápidas</h3>
            
            <div class="o_dashboard_row">
                <div class="o_dashboard_col">
                    <button class="btn btn-danger" t-on-click="openCriticalProducts">
                        🔴 Ver Productos Críticos
                    </button>
                </div>
                <div class="o_dashboard_col">
                    <button class="btn btn-warning" t-on-click="openReorderSuggestions">
                        📋 Ver Sugerencias de Reorden
                    </button>
                </div>
                <div class="o_dashboard_col">
                    <button class="btn btn-info" t-on-click="openLowStockProducts">
                        📦 Ver Productos con Stock Bajo
                    </button>
                </div>
            </div>
        </div>
    </div>

    <!-- Comparación entre Almacenes -->
    <div t-if="comparisonData.comparison_data.length > 1" class="o_dashboard_section">
        <h3>📊 Comparación entre Almacenes</h3>
        
        <div class="o_comparison_table">
            <table class="o_table">
                <thead>
                    <tr>
                        <th>Almacén</th>
                        <th>Eficiencia</th>
                        <th>Rank</th>
                        <th>Productos</th>
                        <th>Críticos</th>
                        <th>Disponibilidad</th>
                        <th>Gasto Mensual</th>
                    </tr>
                </thead>
                <tbody>
                    <tr t-foreach="warehouse in comparisonData.comparison_data" 
                        t-att-class="'o_comparison_row_' + getPerformanceClass(warehouse.performance_rank)">
                        <td><t t-esc="warehouse.warehouse_name"/></td>
                        <td>
                            <div class="o_progress_bar">
                                <div class="o_progress" t-att-style="'width: ' + warehouse.efficiency_score + '%'" />
                                <span><t t-esc="formatDecimal(warehouse.efficiency_score)"/>%</span>
                            </div>
                        </td>
                        <td>#<t t-esc="warehouse.performance_rank"/></td>
                        <td><t t-esc="warehouse.total_products"/></td>
                        <td><t t-esc="warehouse.critical_products"/></td>
                        <td><t t-esc="formatDecimal(warehouse.stock_availability)"/>%</td>
                        <td><t t-esc="formatCurrency(warehouse.monthly_spend)"/></td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div t-if="comparisonData.best_warehouse" class="o_best_warehouse">
            <h4>🏆 Mejor Almacén: <t t-esc="comparisonData.best_warehouse.warehouse_name"/></h4>
        </div>
        
        <div t-if="comparisonData.worst_warehouse" class="o_worst_warehouse">
            <h4>🔴 Peor Almacén: <t t-esc="comparisonData.worst_warehouse.warehouse_name"/></h4>
        </div>
    </div>

    <!-- Loading indicator -->
    <div t-if="loading" class="o_loading_overlay">
        <div class="o_loading">
            <div class="o_loading_spinner"></div>
            <p>Generando inteligencia...</p>
        </div>
    </div>

    <!-- Last update -->
    <div t-if="lastUpdate" class="o_dashboard_footer">
        <small>Última actualización: <t t-esc="lastUpdate"/></small>
    </div>
</div>

<style>
.o_dashboard {
    padding: 20px;
    font-family: Arial, sans-serif;
}

.o_dashboard_header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding: 15px;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 8px;
    color: white;
}

.o_dashboard_header_left h2 {
    margin: 0;
    font-size: 24px;
}

.o_form_label label {
    font-weight: bold;
    margin-right: 10px;
}

#warehouse_selector {
    padding: 8px 12px;
    border: none;
    border-radius: 4px;
    font-size: 14px;
    min-width: 200px;
}

.o_dashboard_header_right button {
    margin-left: 10px;
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
}

.o_dashboard_content {
    margin-bottom: 20px;
}

.o_dashboard_section {
    margin-bottom: 30px;
    padding: 20px;
    background: white;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

.o_dashboard_section h3 {
    margin-top: 0;
    color: #333;
    border-bottom: 2px solid #eee;
    padding-bottom: 10px;
}

.o_dashboard_row {
    display: flex;
    margin-bottom: 20px;
    gap: 20px;
}

.o_dashboard_col {
    flex: 1;
}

.o_dashboard_col_6 {
    flex: 1;
}

.o_stat_box {
    background: #f8f9fa;
    border: 1px solid #e9ecef;
    border-radius: 6px;
    padding: 15px;
    margin-bottom: 10px;
    text-align: center;
}

.o_stat_value {
    font-size: 24px;
    font-weight: bold;
    color: #333;
    margin-bottom: 5px;
}

.o_stat_label {
    font-size: 12px;
    color: #666;
    text-transform: uppercase;
}

.o_stat_primary { background: #d4edda; color: #155724; }
.o_stat_success { background: #d4edda; color: #155724; }
.o_stat_warning { background: #fff3cd; color: #856404; }
.o_stat_danger { background: #f8d7da; color: #721c24; }
.o_stat_info { background: #e2e3f2; color: #383d41; }

.o_alert_box {
    background: #f8d7da;
    border: 1px solid #f5c6cb;
    border-radius: 6px;
    padding: 15px;
    margin-bottom: 10px;
}

.o_alert_title {
    font-size: 18px;
    font-weight: bold;
    color: #721c24;
    margin-bottom: 10px;
}

.o_alert_content {
    font-size: 14px;
    color: #333;
    white-space: pre-line;
}

.o_comparison_table {
    overflow-x: auto;
    margin-bottom: 20px;
}

.o_table {
    width: 100%;
    border-collapse: collapse;
    background: white;
    border-radius: 6px;
    overflow: hidden;
}

.o_table th {
    background: #f8f9fa;
    padding: 12px;
    text-align: left;
    font-weight: bold;
    border-bottom: 2px solid #dee2e6;
}

.o_table td {
    padding: 12px;
    text-align: left;
    border-bottom: 1px solid #dee2e6;
}

.o_comparison_row_success { background: #d4edda; }
.o_comparison_row_warning { background: #fff3cd; }
.o_comparison_row_danger { background: #f8d7da; }

.o_progress_bar {
    width: 100px;
    height: 20px;
    background: #e9ecef;
    border-radius: 10px;
    overflow: hidden;
    position: relative;
}

.o_progress {
    height: 100%;
    background: linear-gradient(90deg, #28a745 0%, #20bf6b 100%);
    border-radius: 10px;
    transition: width 0.3s ease;
}

.o_best_warehouse {
    background: #d4edda;
    color: #155724;
    padding: 15px;
    border-radius: 6px;
    margin-bottom: 20px;
    text-align: center;
}

.o_worst_warehouse {
    background: #f8d7da;
    color: #721c24;
    padding: 15px;
    border-radius: 6px;
    margin-bottom: 20px;
    text-align: center;
}

.o_loading_overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0,0,0,0.5);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 9999;
}

.o_loading {
    background: white;
    padding: 30px;
    border-radius: 8px;
    text-align: center;
}

.o_loading_spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #ccc;
    border-top: 4px solid #667eea;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.o_dashboard_footer {
    text-align: center;
    color: #666;
    margin-top: 20px;
    padding-top: 20px;
    border-top: 1px solid #eee;
}

.btn {
    padding: 8px 16px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-weight: bold;
    transition: all 0.3s ease;
}

.btn:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}

.btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
    transform: none;
    box-shadow: none;
}
</style>
`;

registry.category("actions").add("purchase_intelligence.warehouse_dashboard", WarehouseDashboard);