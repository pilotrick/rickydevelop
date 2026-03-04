/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SupplierPerformanceDashboard extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");

        this.state = useState({
            loading: true,
            data: {
                supplier_metrics: {},
                top_suppliers: [],
                performance_trends: [],
                risk_suppliers: [],
                scorecards: [],
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
                "get_supplier_dashboard_data",
                []
            );
            this.state.data = data;
        } catch (error) {
            console.error("Error loading supplier dashboard:", error);
        } finally {
            this.state.loading = false;
        }
    }

    async refreshData() {
        await this.loadData();
    }

    getScoreClass(score) {
        if (score >= 8.5) return 'text-success';
        if (score >= 7.0) return 'text-warning';
        return 'text-danger';
    }

    getRiskClass(risk) {
        if (risk === 'low') return 'badge-success';
        if (risk === 'medium') return 'badge-warning';
        return 'badge-danger';
    }

    formatCurrency(value) {
        return new Intl.NumberFormat('en-US', {
            style: 'currency',
            currency: 'USD',
            minimumFractionDigits: 0,
            maximumFractionDigits: 0,
        }).format(value);
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

    viewScorecards() {
        this.action.doAction({
            type: 'ir.actions.act_window',
            res_model: 'pi.supplier.scorecard',
            views: [[false, 'list'], [false, 'form']],
            target: 'current',
        });
    }
}

SupplierPerformanceDashboard.template = "purchase_intelligence.SupplierPerformanceDashboard";
registry.category("actions").add("supplier_performance_dashboard", SupplierPerformanceDashboard);
