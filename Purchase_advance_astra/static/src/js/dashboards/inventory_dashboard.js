/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class InventoryIntelligenceDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            data: {
                inventory_metrics: {},
                stock_levels: [],
                abc_analysis: {},
                reorder_suggestions: [],
                stockout_risks: [],
            }
        });

        onWillStart(async () => {
            await this.loadData();
        });
    }

    async loadData() {
        try {
            this.state.loading = true;
            const data = await this.orm.call(
                "purchase.intelligence.kpi",
                "get_inventory_dashboard_data",
                []
            );
            this.state.data = data;
        } catch (error) {
            console.error("Error loading inventory dashboard:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async refreshData() {
        await this.loadData();
    }

    getStockLevelClass(coverage_days) {
        if (coverage_days < 7) return 'text-danger';
        if (coverage_days < 14) return 'text-warning';
        return 'text-success';
    }

    getStockLevelIcon(coverage_days) {
        if (coverage_days < 7) return 'fa-exclamation-triangle';
        if (coverage_days < 14) return 'fa-exclamation-circle';
        return 'fa-check-circle';
    }

    formatCurrency(value) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
    }

    formatNumber(value) {
        return new Intl.NumberFormat('en-US').format(value);
    }

    viewProduct(productId) {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'product.product',
            res_id: productId,
            views: [[false, 'form']],
            target: 'current',
        });
    }

    viewReorderSuggestions() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'pi.automated.order',
            views: [[false, 'list'], [false, 'form']],
            domain: [['state', '=', 'suggested']],
            target: 'current',
        });
    }
}

InventoryIntelligenceDashboard.template = "purchase_intelligence.InventoryIntelligenceDashboard";
registry.category("actions").add("inventory_intelligence_dashboard", InventoryIntelligenceDashboard);
