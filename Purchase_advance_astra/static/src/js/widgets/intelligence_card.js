/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";

/**
 * Visual Intelligence Card Component
 * Displays product intelligence with mini charts and decision indicators
 */
export class VisualIntelligenceCard extends Component {
    setup() {
        this.state = useState({
            expanded: false,
        });
    }

    getRiskColor(risk) {
        const colors = {
            'critical': '#dc2626',
            'high': '#f97316',
            'medium': '#fbbf24',
            'low': '#22c55e',
            'none': '#10b981'
        };
        return colors[risk] || '#6b7280';
    }

    getRiskEmoji(risk) {
        const emojis = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢',
            'none': '✅'
        };
        return emojis[risk] || '⚪';
    }

    getStockStatus(days) {
        if (days <= 0) return { label: 'SIN STOCK', class: 'critical', icon: 'fa-times-circle' };
        if (days <= 3) return { label: 'CRÍTICO', class: 'critical', icon: 'fa-exclamation-circle' };
        if (days <= 7) return { label: 'URGENTE', class: 'high', icon: 'fa-exclamation-triangle' };
        if (days <= 14) return { label: 'BAJO', class: 'medium', icon: 'fa-clock' };
        if (days <= 30) return { label: 'NORMAL', class: 'low', icon: 'fa-check-circle' };
        return { label: 'ÓPTIMO', class: 'good', icon: 'fa-check-circle' };
    }

    getRecommendationAction(stockoutRisk, daysOfStock, needsReorder) {
        if (stockoutRisk === 'critical') {
            return {
                action: 'PEDIR AHORA',
                urgency: 'critical',
                message: 'Stock crítico - Generar orden de compra inmediatamente',
                icon: 'fa-bolt',
                color: '#dc2626'
            };
        }
        if (stockoutRisk === 'high' || needsReorder) {
            return {
                action: 'PEDIR PRONTO',
                urgency: 'high',
                message: 'Por debajo del punto de reorden - Planificar compra',
                icon: 'fa-exclamation',
                color: '#f97316'
            };
        }
        if (daysOfStock <= 14) {
            return {
                action: 'MONITOREAR',
                urgency: 'medium',
                message: 'Stock bajo - Considerar próxima compra',
                icon: 'fa-eye',
                color: '#fbbf24'
            };
        }
        return {
            action: 'OK',
            urgency: 'good',
            message: 'Stock saludable - Sin acción requerida',
            icon: 'fa-check',
            color: '#22c55e'
        };
    }

    toggleExpand() {
        this.state.expanded = !this.state.expanded;
    }
}

VisualIntelligenceCard.template = "purchase_intelligence.VisualIntelligenceCard";
VisualIntelligenceCard.props = {
    product: { type: Object, optional: false },
    showActions: { type: Boolean, optional: true, default: true },
};

registry.category("components").add("purchase_intelligence.VisualIntelligenceCard", VisualIntelligenceCard);

/**
 * Mini Sparkline Chart Component
 * Shows a tiny trend line for quick visualization
 */
export class MiniSparkline extends Component {
    setup() {}

    getChartData() {
        const data = this.props.data || [];
        if (data.length === 0) return null;
        
        const max = Math.max(...data);
        const min = Math.min(...data);
        const range = max - min || 1;
        
        return data.map((value, index) => ({
            x: (index / (data.length - 1)) * 100,
            y: 100 - ((value - min) / range) * 100
        }));
    }

    getPathD() {
        const points = this.getChartData();
        if (!points || points.length === 0) return '';
        
        let d = `M ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x} ${points[i].y}`;
        }
        return d;
    }

    getAreaD() {
        const points = this.getChartData();
        if (!points || points.length === 0) return '';
        
        let d = `M ${points[0].x} 100 L ${points[0].x} ${points[0].y}`;
        for (let i = 1; i < points.length; i++) {
            d += ` L ${points[i].x} ${points[i].y}`;
        }
        d += ` L ${points[points.length - 1].x} 100 Z`;
        return d;
    }

    getColor() {
        const trend = this.props.trend || 'neutral';
        const colors = {
            'up': { stroke: '#dc2626', fill: 'rgba(220, 38, 38, 0.1)' },
            'down': { stroke: '#22c55e', fill: 'rgba(34, 197, 94, 0.1)' },
            'neutral': { stroke: '#3b82f6', fill: 'rgba(59, 130, 246, 0.1)' }
        };
        return colors[trend] || colors.neutral;
    }
}

MiniSparkline.template = "purchase_intelligence.MiniSparkline";
MiniSparkline.props = {
    data: { type: Array, optional: false },
    trend: { type: String, optional: true, default: 'neutral' },
    width: { type: Number, optional: true, default: 80 },
    height: { type: Number, optional: true, default: 24 },
};

registry.category("components").add("purchase_intelligence.MiniSparkline", MiniSparkline);

/**
 * Decision Summary Card Component
 * Shows a clear decision summary with action recommendation
 */
export class DecisionSummaryCard extends Component {
    setup() {}

    getUrgencyClass() {
        const urgency = this.props.decision?.urgency || 'good';
        return `decision-card-${urgency}`;
    }

    getIconClass() {
        return this.props.decision?.icon || 'fa-check';
    }
}

DecisionSummaryCard.template = "purchase_intelligence.DecisionSummaryCard";
DecisionSummaryCard.props = {
    decision: { type: Object, optional: false },
    product: { type: Object, optional: false },
};

registry.category("components").add("purchase_intelligence.DecisionSummaryCard", DecisionSummaryCard);

/**
 * Stock Gauge Component
 * Visual gauge showing stock level status
 */
export class StockGauge extends Component {
    setup() {}

    getPercentage() {
        const current = this.props.current || 0;
        const max = this.props.max || 100;
        return Math.min(100, Math.max(0, (current / max) * 100));
    }

    getColor() {
        const percentage = this.getPercentage();
        if (percentage <= 10) return '#dc2626';
        if (percentage <= 25) return '#f97316';
        if (percentage <= 50) return '#fbbf24';
        return '#22c55e';
    }

    getLabel() {
        const percentage = this.getPercentage();
        if (percentage <= 10) return 'CRÍTICO';
        if (percentage <= 25) return 'BAJO';
        if (percentage <= 50) return 'MODERADO';
        return 'ÓPTIMO';
    }
}

StockGauge.template = "purchase_intelligence.StockGauge";
StockGauge.props = {
    current: { type: Number, optional: false },
    max: { type: Number, optional: false },
    showLabel: { type: Boolean, optional: true, default: true },
};

registry.category("components").add("purchase_intelligence.StockGauge", StockGauge);

/**
 * Warehouse Intelligence Mini Dashboard
 * Compact dashboard for showing warehouse-level intelligence
 */
export class WarehouseMiniDashboard extends Component {
    setup() {}

    getWarehouseStats() {
        const warehouses = this.props.warehouses || [];
        return warehouses.map(wh => ({
            ...wh,
            statusClass: this.getStatusClass(wh.stockout_risk, wh.days_of_stock),
            actionRequired: wh.needs_reorder,
        }));
    }

    getStatusClass(risk, days) {
        if (risk === 'critical' || days <= 0) return 'status-critical';
        if (risk === 'high' || days <= 7) return 'status-high';
        if (risk === 'medium' || days <= 14) return 'status-medium';
        return 'status-good';
    }

    getTotalStats() {
        const warehouses = this.props.warehouses || [];
        return {
            totalStock: warehouses.reduce((sum, wh) => sum + (wh.qty_available || 0), 0),
            needsReorder: warehouses.filter(wh => wh.needs_reorder).length,
            criticalCount: warehouses.filter(wh => wh.stockout_risk === 'critical').length,
            avgDaysOfStock: warehouses.length > 0 
                ? warehouses.reduce((sum, wh) => sum + (wh.days_of_stock || 0), 0) / warehouses.length 
                : 0,
        };
    }
}

WarehouseMiniDashboard.template = "purchase_intelligence.WarehouseMiniDashboard";
WarehouseMiniDashboard.props = {
    warehouses: { type: Array, optional: false },
    productName: { type: String, optional: true, default: '' },
};

registry.category("components").add("purchase_intelligence.WarehouseMiniDashboard", WarehouseMiniDashboard);
