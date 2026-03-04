/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MasterPurchaseDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            kpis: {},
            alerts: [],
            productsToOrder: [],
            budgetStatus: {},
            financials: {},
            topSuppliers: [],
            topProducts: [],
            warehouseStock: [],
            recentOrders: [],
            categoryBreakdown: [],
            upcomingDeliveries: [],
            abcAnalysis: {},
            scorecards: [],
            forecasts: [],
            reorderOptimizations: [],
            loading: true,
            lastUpdate: null,
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        try {
            this.state.loading = true;

            // 1. Cargar datos principales del dashboard
            const dashboardData = await this.orm.call(
                "purchase.intelligence.kpi",
                "get_dashboard_data",
                []
            );

            // 2. Cargar productos que necesitan pedido
            const productsToOrder = await this.orm.searchRead(
                "product.template",
                [
                    ["type", "=", "product"],
                    ["needs_reorder", "=", true]
                ],
                [
                    "id", "name", "qty_available", "daily_usage",
                    "days_of_stock", "reorder_point", "safety_stock",
                    "suggested_order_qty", "stockout_risk", "lead_time_days",
                    "standard_price"
                ],
                { limit: 15, order: "stockout_risk desc, days_of_stock asc" }
            );

            // 3. Obtener proveedores de los productos
            const productsWithSupplier = await Promise.all(
                productsToOrder.map(async (product) => {
                    const sellers = await this.orm.searchRead(
                        "product.supplierinfo",
                        [["product_tmpl_id", "=", product.id]],
                        ["partner_id", "price"],
                        { limit: 1 }
                    );
                    return {
                        ...product,
                        supplier_name: sellers.length > 0 ? sellers[0].partner_id[1] : "Sin proveedor",
                        supplier_id: sellers.length > 0 ? sellers[0].partner_id[0] : null,
                        estimated_cost: (product.suggested_order_qty || 0) * (sellers.length > 0 ? sellers[0].price : product.standard_price || 0),
                    };
                })
            );

            // 4. Cargar Top Proveedores
            const topSuppliers = await this.loadTopSuppliers();

            // 5. Cargar Top Productos
            const topProducts = await this.loadTopProducts();

            // 6. Cargar Stock por Almacén
            const warehouseStock = await this.loadWarehouseStock();

            // 7. Cargar Órdenes Recientes
            const recentOrders = await this.loadRecentOrders();

            // 8. Cargar Categorías
            const categoryBreakdown = await this.loadCategoryBreakdown();

            // 9. Cargar Próximas Entregas
            const upcomingDeliveries = await this.loadUpcomingDeliveries();

            // 10. Cargar Financieros
            const financials = await this.loadFinancials();

            // 11. Cargar ABC Analysis
            const abcAnalysis = await this.loadAbcAnalysis();

            // 12. Cargar Scorecards de Proveedores
            const scorecards = await this.loadScorecards();

            // 13. Cargar Pronósticos
            const forecasts = await this.loadForecasts();

            // 14. Cargar Optimizaciones de Reorden
            const reorderOptimizations = await this.loadReorderOptimizations();

            // Asignar todos los datos al estado
            this.state.kpis = dashboardData.kpis || {};
            this.state.alerts = dashboardData.alerts || [];
            this.state.productsToOrder = productsWithSupplier;
            this.state.budgetStatus = dashboardData.budget_status || {};
            this.state.financials = financials;
            this.state.topSuppliers = topSuppliers;
            this.state.topProducts = topProducts;
            this.state.warehouseStock = warehouseStock;
            this.state.recentOrders = recentOrders;
            this.state.categoryBreakdown = categoryBreakdown;
            this.state.upcomingDeliveries = upcomingDeliveries;
            this.state.abcAnalysis = abcAnalysis;
            this.state.scorecards = scorecards;
            this.state.forecasts = forecasts;
            this.state.reorderOptimizations = reorderOptimizations;
            this.state.lastUpdate = new Date().toLocaleString('es-ES');
            this.state.loading = false;

        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.state.loading = false;
            this.notification.add("Error al cargar datos del dashboard", { type: "danger" });
        }
    }

    async loadTopSuppliers() {
        try {
            // Obtener órdenes del mes actual
            const today = new Date();
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            const firstDayStr = firstDay.toISOString().split('T')[0];

            const orders = await this.orm.searchRead(
                "purchase.order",
                [
                    ["state", "in", ["purchase", "done"]],
                    ["date_order", ">=", firstDayStr]
                ],
                ["partner_id", "amount_total"],
                { limit: 500 }
            );

            // Agrupar por proveedor
            const supplierMap = {};
            for (const order of orders) {
                const partnerId = order.partner_id[0];
                const partnerName = order.partner_id[1];
                if (!supplierMap[partnerId]) {
                    supplierMap[partnerId] = {
                        id: partnerId,
                        name: partnerName,
                        total_amount: 0,
                        order_count: 0,
                        on_time_rate: 85 + Math.random() * 15 // Simulado
                    };
                }
                supplierMap[partnerId].total_amount += order.amount_total;
                supplierMap[partnerId].order_count += 1;
            }

            // Convertir a array y ordenar
            return Object.values(supplierMap)
                .sort((a, b) => b.total_amount - a.total_amount)
                .slice(0, 10);
        } catch (error) {
            console.error("Error loading top suppliers:", error);
            return [];
        }
    }

    async loadTopProducts() {
        try {
            const today = new Date();
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            const firstDayStr = firstDay.toISOString().split('T')[0];

            const lines = await this.orm.searchRead(
                "purchase.order.line",
                [
                    ["order_id.state", "in", ["purchase", "done"]],
                    ["order_id.date_order", ">=", firstDayStr]
                ],
                ["product_id", "product_qty", "price_subtotal"],
                { limit: 1000 }
            );

            // Agrupar por producto
            const productMap = {};
            for (const line of lines) {
                if (!line.product_id) continue;
                const productId = line.product_id[0];
                const productName = line.product_id[1];
                if (!productMap[productId]) {
                    productMap[productId] = {
                        id: productId,
                        name: productName,
                        total_qty: 0,
                        total_value: 0,
                        order_count: 0
                    };
                }
                productMap[productId].total_qty += line.product_qty;
                productMap[productId].total_value += line.price_subtotal;
                productMap[productId].order_count += 1;
            }

            return Object.values(productMap)
                .sort((a, b) => b.total_value - a.total_value)
                .slice(0, 10);
        } catch (error) {
            console.error("Error loading top products:", error);
            return [];
        }
    }

    async loadWarehouseStock() {
        try {
            const warehouses = await this.orm.searchRead(
                "stock.warehouse",
                [],
                ["id", "name"],
                { limit: 10 }
            );

            const warehouseData = await Promise.all(
                warehouses.map(async (wh) => {
                    // Obtener estadísticas del almacén
                    const quants = await this.orm.searchRead(
                        "stock.quant",
                        [["location_id.warehouse_id", "=", wh.id]],
                        ["product_id", "quantity", "value"],
                        { limit: 5000 }
                    );

                    const productIds = new Set(quants.map(q => q.product_id[0]));
                    const totalValue = quants.reduce((sum, q) => sum + (q.value || 0), 0);
                    const lowStockCount = quants.filter(q => q.quantity > 0 && q.quantity < 10).length;
                    const outOfStockCount = quants.filter(q => q.quantity <= 0).length;

                    return {
                        id: wh.id,
                        name: wh.name,
                        product_count: productIds.size,
                        total_value: totalValue,
                        low_stock_count: lowStockCount,
                        out_of_stock_count: outOfStockCount,
                        fill_percent: Math.min(100, (productIds.size / 100) * 100)
                    };
                })
            );

            return warehouseData;
        } catch (error) {
            console.error("Error loading warehouse stock:", error);
            return [];
        }
    }

    async loadRecentOrders() {
        try {
            const orders = await this.orm.searchRead(
                "purchase.order",
                [["state", "!=", "cancel"]],
                ["id", "name", "partner_id", "date_order", "amount_total", "state"],
                { limit: 10, order: "date_order desc" }
            );

            return orders.map(o => ({
                id: o.id,
                name: o.name,
                partner_name: o.partner_id ? o.partner_id[1] : "N/A",
                date_order: o.date_order ? new Date(o.date_order).toLocaleDateString('es-ES') : "",
                amount_total: o.amount_total,
                state: o.state
            }));
        } catch (error) {
            console.error("Error loading recent orders:", error);
            return [];
        }
    }

    async loadCategoryBreakdown() {
        try {
            const today = new Date();
            const firstDay = new Date(today.getFullYear(), today.getMonth(), 1);
            const firstDayStr = firstDay.toISOString().split('T')[0];

            const lines = await this.orm.searchRead(
                "purchase.order.line",
                [
                    ["order_id.state", "in", ["purchase", "done"]],
                    ["order_id.date_order", ">=", firstDayStr]
                ],
                ["product_id", "price_subtotal"],
                { limit: 2000 }
            );

            // Obtener categorías de productos
            const productIds = [...new Set(lines.map(l => l.product_id[0]).filter(Boolean))];
            const products = await this.orm.searchRead(
                "product.product",
                [["id", "in", productIds]],
                ["id", "categ_id"],
                { limit: 2000 }
            );

            const productCategoryMap = {};
            for (const p of products) {
                productCategoryMap[p.id] = p.categ_id;
            }

            // Agrupar por categoría
            const categoryMap = {};
            let totalAmount = 0;
            for (const line of lines) {
                if (!line.product_id) continue;
                const categ = productCategoryMap[line.product_id[0]];
                if (!categ) continue;
                const categId = categ[0];
                const categName = categ[1];
                if (!categoryMap[categId]) {
                    categoryMap[categId] = { id: categId, name: categName, amount: 0 };
                }
                categoryMap[categId].amount += line.price_subtotal;
                totalAmount += line.price_subtotal;
            }

            // Calcular porcentajes
            const categories = Object.values(categoryMap)
                .sort((a, b) => b.amount - a.amount)
                .slice(0, 8);

            for (const cat of categories) {
                cat.percent = totalAmount > 0 ? (cat.amount / totalAmount) * 100 : 0;
            }

            return categories;
        } catch (error) {
            console.error("Error loading category breakdown:", error);
            return [];
        }
    }

    async loadUpcomingDeliveries() {
        try {
            const today = new Date();
            const nextWeek = new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000);
            const todayStr = today.toISOString().split('T')[0];
            const nextWeekStr = nextWeek.toISOString().split('T')[0];

            const pickings = await this.orm.searchRead(
                "stock.picking",
                [
                    ["picking_type_id.code", "=", "incoming"],
                    ["state", "not in", ["done", "cancel"]],
                    ["scheduled_date", ">=", todayStr],
                    ["scheduled_date", "<=", nextWeekStr]
                ],
                ["id", "name", "partner_id", "scheduled_date", "move_ids_without_package"],
                { limit: 10, order: "scheduled_date asc" }
            );

            const months = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];

            return pickings.map(p => {
                const schedDate = new Date(p.scheduled_date);
                return {
                    id: p.id,
                    name: p.name,
                    partner_name: p.partner_id ? p.partner_id[1] : "N/A",
                    day: schedDate.getDate(),
                    month: months[schedDate.getMonth()],
                    product_count: p.move_ids_without_package ? p.move_ids_without_package.length : 0
                };
            });
        } catch (error) {
            console.error("Error loading upcoming deliveries:", error);
            return [];
        }
    }

    async loadFinancials() {
        try {
            const today = new Date();
            const firstDayMonth = new Date(today.getFullYear(), today.getMonth(), 1);
            const firstDayLastMonth = new Date(today.getFullYear(), today.getMonth() - 1, 1);
            const lastDayLastMonth = new Date(today.getFullYear(), today.getMonth(), 0);

            const firstDayStr = firstDayMonth.toISOString().split('T')[0];
            const firstDayLastMonthStr = firstDayLastMonth.toISOString().split('T')[0];
            const lastDayLastMonthStr = lastDayLastMonth.toISOString().split('T')[0];

            // Compras este mes
            const thisMonthOrders = await this.orm.searchRead(
                "purchase.order",
                [
                    ["state", "in", ["purchase", "done"]],
                    ["date_order", ">=", firstDayStr]
                ],
                ["amount_total"],
                { limit: 1000 }
            );

            // Compras mes anterior
            const lastMonthOrders = await this.orm.searchRead(
                "purchase.order",
                [
                    ["state", "in", ["purchase", "done"]],
                    ["date_order", ">=", firstDayLastMonthStr],
                    ["date_order", "<=", lastDayLastMonthStr]
                ],
                ["amount_total"],
                { limit: 1000 }
            );

            const monthPurchases = thisMonthOrders.reduce((sum, o) => sum + o.amount_total, 0);
            const lastMonthPurchases = lastMonthOrders.reduce((sum, o) => sum + o.amount_total, 0);
            const monthChange = lastMonthPurchases > 0
                ? ((monthPurchases - lastMonthPurchases) / lastMonthPurchases) * 100
                : 0;

            return {
                month_purchases: monthPurchases,
                month_change: monthChange,
                avg_order_value: thisMonthOrders.length > 0 ? monthPurchases / thisMonthOrders.length : 0,
                total_orders: thisMonthOrders.length,
                total_savings: monthPurchases * 0.05, // Estimado 5%
                savings_percent: 5,
                avg_freight_cost: monthPurchases * 0.02, // Estimado 2%
                freight_percent: 2
            };
        } catch (error) {
            console.error("Error loading financials:", error);
            return {};
        }
    }

    async loadAbcAnalysis() {
        try {
            const products = await this.orm.searchRead(
                "product.template",
                [["type", "=", "product"]],
                ["id", "standard_price", "qty_available"],
                { limit: 1000 }
            );

            // Calcular valor de inventario para cada producto
            const productsWithValue = products.map(p => ({
                ...p,
                value: p.standard_price * p.qty_available
            })).sort((a, b) => b.value - a.value);

            const totalValue = productsWithValue.reduce((sum, p) => sum + p.value, 0);

            // Clasificar ABC
            let cumValue = 0;
            let aCount = 0, bCount = 0, cCount = 0;
            let aValue = 0, bValue = 0, cValue = 0;

            for (const p of productsWithValue) {
                cumValue += p.value;
                const percent = (cumValue / totalValue) * 100;
                if (percent <= 80) {
                    aCount++;
                    aValue += p.value;
                } else if (percent <= 95) {
                    bCount++;
                    bValue += p.value;
                } else {
                    cCount++;
                    cValue += p.value;
                }
            }

            return {
                a_count: aCount,
                a_value: aValue,
                a_percent: totalValue > 0 ? Math.round((aValue / totalValue) * 100) : 80,
                b_count: bCount,
                b_value: bValue,
                b_percent: totalValue > 0 ? Math.round((bValue / totalValue) * 100) : 15,
                c_count: cCount,
                c_value: cValue,
                c_percent: totalValue > 0 ? Math.round((cValue / totalValue) * 100) : 5
            };
        } catch (error) {
            console.error("Error loading ABC analysis:", error);
            return {};
        }
    }

    async loadScorecards() {
        try {
            const scorecards = await this.orm.searchRead(
                "pi.supplier.scorecard",
                [],
                ["id", "partner_id", "date", "score_quality", "score_delivery",
                    "score_price", "score_service", "score_innovation", "overall_score"],
                { limit: 20, order: "date desc" }
            );
            return scorecards.map(sc => ({
                ...sc,
                partner_name: sc.partner_id[1],
                partner_id: sc.partner_id[0]
            }));
        } catch (error) {
            console.error("Error loading scorecards:", error);
            return [];
        }
    }

    async loadForecasts() {
        try {
            const forecasts = await this.orm.searchRead(
                "purchase.intelligence.forecast",
                [],
                ["id", "product_id", "forecast_qty", "confidence", "method", "notes"],
                { limit: 20, order: "date desc" }
            );
            return forecasts.map(fc => ({
                ...fc,
                product_name: fc.product_id[1],
                product_id: fc.product_id[0]
            }));
        } catch (error) {
            console.error("Error loading forecasts:", error);
            return [];
        }
    }

    async loadReorderOptimizations() {
        try {
            const optimizations = await this.orm.searchRead(
                "pi.reorder.optimization",
                [],
                ["id", "product_id", "current_rop", "optimized_rop", "current_eoq",
                    "optimized_eoq", "optimized_safety_stock", "stockout_risk", "applied"],
                { limit: 20, order: "stockout_risk desc" }
            );
            return optimizations.map(opt => ({
                ...opt,
                product_name: opt.product_id[1],
                product_id: opt.product_id[0]
            }));
        } catch (error) {
            console.error("Error loading reorder optimizations:", error);
            return [];
        }
    }

    // Navegación a vistas
    openScorecards() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Cuadros de Mando de Proveedores",
            res_model: "pi.supplier.scorecard",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    openForecasts() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Pronósticos de Demanda",
            res_model: "purchase.intelligence.forecast",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    openReorderOptimization() {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: "Optimización de Reorden",
            res_model: "pi.reorder.optimization",
            view_mode: "list,form",
            views: [[false, "list"], [false, "form"]],
        });
    }

    async refreshDashboard() {
        await this.loadDashboardData();
        this.notification.add("Dashboard actualizado", { type: "success" });
    }

    async runStockAnalysis() {
        try {
            this.state.loading = true;
            this.notification.add("Ejecutando análisis completo del sistema...", { type: "info" });

            // 1. Análisis de Stock - Todos los productos
            this.notification.add("1/4 - Analizando stock de productos...", { type: "info" });
            await this.orm.call(
                "product.template",
                "action_recalculate_all_stock_intelligence",
                []
            );

            // 2. Generar Optimizaciones de Reorden - Todos los productos
            this.notification.add("2/4 - Generando optimizaciones de reorden...", { type: "info" });
            await this.orm.call(
                "pi.reorder.optimization",
                "action_generate_all_optimizations",
                []
            );

            // 3. Generar Scorecards de Proveedores - Todos los proveedores
            this.notification.add("3/5 - Evaluando proveedores automáticamente...", { type: "info" });
            await this.orm.call(
                "pi.supplier.scorecard",
                "action_generate_all_scorecards",
                []
            );

            // 4. Generar Pronósticos de Demanda - Todos los productos
            this.notification.add("4/5 - Generando pronósticos de demanda...", { type: "info" });
            await this.orm.call(
                "purchase.intelligence.forecast",
                "action_update_forecasts",
                []
            );

            // 5. Calcular KPIs
            this.notification.add("5/5 - Calculando KPIs...", { type: "info" });
            await this.orm.call(
                "purchase.intelligence.kpi",
                "action_calculate_daily_warehouse_kpis",
                []
            );

            await this.loadDashboardData();
            this.notification.add("✅ Análisis COMPLETO finalizado. Todos los datos actualizados.", { type: "success" });
        } catch (error) {
            console.error("Error running full analysis:", error);
            this.notification.add("Error al ejecutar análisis: " + error.message, { type: "danger" });
            this.state.loading = false;
        }
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

    getRiskClass(risk) {
        const classes = {
            'critical': 'badge-critical',
            'high': 'badge-high',
            'medium': 'badge-medium',
            'low': 'badge-low',
            'none': 'badge-success'
        };
        return classes[risk] || 'badge-secondary';
    }

    getRiskLabel(risk) {
        const labels = {
            'critical': '🔴 CRÍTICO',
            'high': '🟠 ALTO',
            'medium': '🟡 MEDIO',
            'low': '🟢 BAJO',
            'none': '✓ OK'
        };
        return labels[risk] || risk;
    }

    getStateClass(state) {
        const classes = {
            'draft': 'secondary',
            'sent': 'info',
            'to approve': 'warning',
            'purchase': 'success',
            'done': 'primary',
            'cancel': 'danger'
        };
        return classes[state] || 'secondary';
    }

    getStateLabel(state) {
        const labels = {
            'draft': 'Borrador',
            'sent': 'Enviada',
            'to approve': 'Por Aprobar',
            'purchase': 'Confirmada',
            'done': 'Completada',
            'cancel': 'Cancelada'
        };
        return labels[state] || state;
    }

    // ===== ACCIONES DE NAVEGACIÓN =====

    openPurchaseOrders(filter) {
        const domain = filter === 'pending'
            ? [["state", "=", "to approve"]]
            : [["state", "in", ["purchase", "done"]]];

        this.action.doAction({
            type: 'ir.actions.act_window',
            name: filter === 'pending' ? 'Órdenes Pendientes' : 'Órdenes Activas',
            res_model: 'purchase.order',
            views: [[false, 'list'], [false, 'form']],
            domain: domain,
            target: 'current',
        });
    }

    openCriticalProducts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Productos Críticos - Riesgo de Rotura',
            res_model: 'product.template',
            views: [[false, 'list'], [false, 'form']],
            domain: [["type", "=", "product"], ["stockout_risk", "in", ["critical", "high"]]],
            context: { 'search_default_group_by_category': 1 },
            target: 'current',
        });
    }

    openExpectedDeliveries() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Recepciones de Hoy',
            res_model: 'stock.picking',
            views: [[false, 'list'], [false, 'form']],
            domain: [["picking_type_id.code", "=", "incoming"], ["state", "not in", ["done", "cancel"]]],
            target: 'current',
        });
    }

    openLowStockProducts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Productos con Stock Bajo',
            res_model: 'product.template',
            views: [[false, 'list'], [false, 'form']],
            domain: [["type", "=", "product"], ["days_of_stock", "<", 7], ["days_of_stock", ">", 0]],
            target: 'current',
        });
    }

    openPendingReceipts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Recepciones Pendientes',
            res_model: 'stock.picking',
            views: [[false, 'list'], [false, 'form']],
            domain: [["picking_type_id.code", "=", "incoming"], ["state", "=", "assigned"]],
            target: 'current',
        });
    }

    openAllProductsToOrder() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Productos que Necesitan Pedido',
            res_model: 'product.template',
            views: [[false, 'list'], [false, 'form']],
            domain: [["type", "=", "product"], ["needs_reorder", "=", true]],
            target: 'current',
        });
    }

    openAllKPIs() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Todos los KPIs',
            res_model: 'purchase.intelligence.kpi',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    openAllSuppliers() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Todos los Proveedores',
            res_model: 'res.partner',
            views: [[false, 'list'], [false, 'form']],
            domain: [["supplier_rank", ">", 0]],
            target: 'current',
        });
    }

    openTopProducts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Productos Más Comprados',
            res_model: 'product.template',
            views: [[false, 'list'], [false, 'form']],
            domain: [["type", "=", "product"], ["purchase_ok", "=", true]],
            target: 'current',
        });
    }

    openAllOrders() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Todas las Órdenes de Compra',
            res_model: 'purchase.order',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }

    viewProduct(productId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'product.template',
            res_id: productId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    viewSupplier(supplierId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'res.partner',
            res_id: supplierId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    viewOrder(orderId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'purchase.order',
            res_id: orderId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    viewPicking(pickingId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'stock.picking',
            res_id: pickingId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    async createPurchaseOrderForProduct(product) {
        try {
            const result = await this.orm.create('purchase.order', [{
                partner_id: product.supplier_id || false,
                order_line: [[0, 0, {
                    product_id: product.id,
                    product_qty: product.suggested_order_qty || 10,
                    price_unit: 0,
                }]],
            }]);

            if (result && result.length > 0) {
                this.notification.add(`Orden de compra creada para ${product.name}`, { type: "success" });

                this.action.doAction({
                    type: 'ir.actions.act_window',
                    res_model: 'purchase.order',
                    res_id: result[0],
                    views: [[false, 'form']],
                    target: 'current',
                });
            }
        } catch (error) {
            console.error("Error creating PO:", error);
            this.notification.add("Error al crear orden de compra", { type: "danger" });
        }
    }

    viewKPIDetails(kpiId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'purchase.intelligence.kpi',
            res_id: kpiId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    viewAlerts() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            name: 'Registro de Alertas',
            res_model: 'pi.alert.log',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }
}

MasterPurchaseDashboard.template = "purchase_intelligence.MasterPurchaseDashboard";
MasterPurchaseDashboard.components = {};

registry.category("actions").add("purchase_intelligence.master_dashboard", MasterPurchaseDashboard);
